"""
On-demand local cache for remote (SFTP) files.

A remote file is copied into a local folder that mirrors the remote layout, so
`cache/<host>/home/user/tools/x.cwl` sits where `/home/user/tools/x.cwl` lives
on the server. Relative references (`run:`, `$import`, `$include`) therefore
resolve exactly as they do on the server, and every consumer - schema-salad,
cwltool, jshint, the filesystem APIs - works on plain local paths.

Only what is needed is copied:
  * `fetch_closure` copies one document plus the files it references, transitively.
  * `fetch` re-downloads a file only when its size or modification time changed.

Saving goes through `push`, which refuses to overwrite a file that changed on
the server since it was last fetched (`RemoteConflictError`).
"""

import json
import logging
import os
import re
import shutil
import threading
import time
import contextlib
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from platformdirs import user_cache_dir
from ruamel.yaml import YAML

import remote
from remote import RemoteError

logger = logging.getLogger(__name__)

CACHE_ROOT = Path(user_cache_dir('cwled')) / 'remote'
INDEX_NAME = 'index.json'
# A cached copy is trusted without asking the server for this many seconds after
# it was last checked. Opening, switching tabs and parsing steps all reload the
# document, so without this every one of them would wait for a round trip.
CHECK_INTERVAL = 60.0
_last_checked: dict = {}


_progress = threading.local()


@contextlib.contextmanager
def progress_listener(listener):
    """
    Receive progress from `fetch_closure` while the block runs.

    The listener is called as `listener(done, total, name, contacted)` once per file
    considered; `contacted` is False when the cached copy was trusted without asking
    the server.
    """
    previous = getattr(_progress, 'listener', None)
    _progress.listener = listener
    try:
        yield
    finally:
        _progress.listener = previous


class RemoteConflictError(RemoteError):
    """The server copy changed (or disappeared) since cwled last fetched it."""


def _canonical(uri) -> str:
    """The stable URI used as the cache key (fragments removed, path normalised)."""
    return remote.canonical(uri)


def cache_path(uri) -> Path:
    """
    Local path where a remote file is cached.

    Args:
        uri: sftp:// location of the file.

    Returns:
        Path: `<CACHE_ROOT>/<user@host:port>/<remote absolute path>`.
    """
    parts = urlsplit(_canonical(uri))
    # plain characters only: file:// URIs percent-encode '@' and ':', which would not match
    authority = re.sub(r'[^A-Za-z0-9._-]', '_', parts.netloc)
    return CACHE_ROOT / authority / parts.path.lstrip('/')


def _index_path() -> Path:
    return CACHE_ROOT / INDEX_NAME


def _load_index() -> dict:
    try:
        return json.loads(_index_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _save_index(index: dict) -> None:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = _index_path().with_suffix('.tmp')
    tmp.write_text(json.dumps(index, indent=1, sort_keys=True), encoding='utf-8')
    os.replace(tmp, _index_path())


def known_stamp(uri):
    """
    The (mtime, size) recorded when the file was last fetched or saved, without
    contacting the server. None if the file has never been cached.
    """
    stamp = _load_index().get(_canonical(uri))
    return tuple(stamp) if stamp else None


def _stamp(remote_file) -> list:
    """(mtime, size) of a remote file: the signature used to detect server-side changes."""
    info = remote_file.stat()
    return [float(info.st_mtime), int(info.st_size)]


def fetch(uri) -> Path:
    """
    Make sure the local copy of one remote file is current.

    Args:
        uri: sftp:// location of the file.

    Returns:
        Path: the local copy.
    """
    return _fetch(uri)[0]


def _fetch(uri) -> tuple:
    """Like `fetch`, also returning whether the server was contacted (checked or downloaded)."""
    key = _canonical(uri)
    local = cache_path(key)
    index = _load_index()
    recently_checked = time.monotonic() - _last_checked.get(key, -CHECK_INTERVAL) < CHECK_INTERVAL
    if local.is_file() and key in index and recently_checked:
        return local, False
    remote_file = remote.to_path(key)
    try:
        stamp = _stamp(remote_file)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise FileNotFoundError(f"{key} cannot be read on the server: {exc}") from exc
    _last_checked[key] = time.monotonic()
    if local.is_file() and index.get(key) == stamp:
        return local, True  # checked on the server; nothing to download
    local.parent.mkdir(parents=True, exist_ok=True)
    partial = local.with_name(local.name + '.part')
    with remote_file.open('rb') as src, open(partial, 'wb') as dst:
        shutil.copyfileobj(src, dst)
    os.replace(partial, local)
    index[key] = stamp
    _save_index(index)
    logger.info(f"Fetched {key} into {local}")
    return local, True


def _references_of(local: Path):
    """Yield the file references of a local document; unreadable files have none."""
    text = local.read_text(encoding='utf-8')
    try:
        if text.lstrip().startswith('{'):
            loaded = json.loads(text)
        else:
            loaded = YAML(typ='safe').load(text)
    except Exception:
        logger.debug(f"No references read from {local}", exc_info=True)
        return
    yield from remote._references(loaded or {})


def fetch_closure(uri) -> Path:
    """
    Fetch a remote document and every file it references, transitively.

    Args:
        uri: sftp:// location of the document.

    Returns:
        Path: the local copy of the document.
    """
    root = _canonical(uri)
    queue = [root]
    seen = {root}
    processed = 0
    listener = getattr(_progress, 'listener', None)
    while queue:
        current = queue.pop()
        local, contacted = _fetch(current)
        processed += 1
        if listener:
            listener(done=processed, total=len(seen), name=Path(current).name, contacted=contacted)
        for reference in _references_of(local):
            if urlsplit(reference).scheme:
                continue  # http(s) and other absolute identifiers are not fetched
            target = _canonical(remote.normalise_remote_join(current, reference))
            if target not in seen:
                seen.add(target)
                queue.append(target)
    logger.info(f"Cached {len(seen)} file(s) for {root}")
    return cache_path(root)


def pending_path(uri) -> Path:
    """Local staging file for a save that has not reached the server yet."""
    local = cache_path(uri)
    return local.with_name(f".{local.name}.{uuid.uuid4().hex[:8]}.pending")


def push(uri, source: Path, force: bool = False) -> None:
    """
    Upload a locally saved file to the server, unless the server copy changed.

    On success the cache copy is replaced with `source` and the index is updated.

    Args:
        uri: sftp:// destination.
        source (Path): the complete new content, on local disk.
        force (bool): overwrite even if the server copy changed (used for Save As
            onto a file the user explicitly chose).

    Raises:
        RemoteConflictError: the server copy changed since the last fetch.
    """
    key = _canonical(uri)
    remote_file = remote.to_path(key)
    index = _load_index()
    known = index.get(key)
    if not force:
        if remote_file.exists():
            if _stamp(remote_file) != known:
                raise RemoteConflictError(
                    f"{key} changed on the server since it was opened. "
                    "Save As to a new file to keep your version.")
        elif known is not None:
            raise RemoteConflictError(f"{key} was removed on the server.")

    temp = remote_file.parent / f".{remote_file.name}.{uuid.uuid4().hex[:8]}.tmp"
    with open(source, 'rb') as src, temp.open('wb') as dst:
        shutil.copyfileobj(src, dst)
    remote.replace_file(temp, remote_file)

    local = cache_path(key)
    local.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, local)
    index[key] = _stamp(remote_file)
    _save_index(index)
    logger.info(f"Saved {key} to the server")
