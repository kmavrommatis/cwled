"""
Remote (SFTP) workspace support.

Remote files are addressed with `sftp://user@host:port/absolute/path` URIs and
handled as universal_pathlib `UPath` objects. Local files stay `pathlib.Path`.
Everything that accepts a file location should go through `to_path()` and
`to_uri()` so the two kinds stay interchangeable.

Connections come from three sources:
  a) a Host entry in ~/.ssh/config,
  b) host + username + SSH key (+ optional key passphrase),
  c) host + username + password.

Passwords and passphrases are only kept in memory for the life of the
connection. Only the non-secret fields of a profile are ever persisted.

Host keys are verified. Unknown keys raise `UnknownHostKeyError` so the UI can
show the fingerprint and ask the user to trust it; trusted keys are stored in
cwled's own known_hosts file. fsspec's default (`auto_add`) is deliberately
not used.
"""

import base64
import contextlib
import hashlib
import logging
import os
import posixpath
import shutil
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator, Optional, Union
from urllib.parse import urlsplit

import fsspec
import paramiko
from fsspec.implementations.sftp import SFTPFileSystem
from platformdirs import user_config_dir
from upath import UPath

logger = logging.getLogger(__name__)

URI_PREFIX = 'sftp://'
DEFAULT_PORT = 22
SSH_CONFIG_PATH = Path.home() / '.ssh' / 'config'
SYSTEM_KNOWN_HOSTS = Path.home() / '.ssh' / 'known_hosts'


class RemoteError(Exception):
    """Base class for failures talking to a remote workspace."""


class RemoteNotConnected(RemoteError):
    """A remote path was used before its connection was opened."""


class UnknownHostKeyError(RemoteError):
    """
    The server presented a host key that is not yet trusted.

    Attributes:
        hostname (str): host name as paramiko reports it (may be `[host]:port`).
        key (paramiko.PKey): the key offered by the server.
    """

    def __init__(self, hostname: str, key: paramiko.PKey):
        super().__init__(f"Unknown host key for {hostname}")
        self.hostname = hostname
        self.key = key

    @property
    def fingerprint(self) -> str:
        """SHA256 fingerprint in the same format OpenSSH prints."""
        digest = hashlib.sha256(self.key.asbytes()).digest()
        return 'SHA256:' + base64.b64encode(digest).decode().rstrip('=')


class HostKeyMismatchError(RemoteError):
    """The server's key differs from the one already trusted. Never auto-accepted."""


def cwled_known_hosts_path() -> Path:
    """Location of the known_hosts file cwled writes trusted keys to."""
    return Path(user_config_dir('cwled')) / 'known_hosts'


class _PromptForTrustPolicy(paramiko.MissingHostKeyPolicy):
    """Turns an unknown host key into an UnknownHostKeyError the UI can handle."""

    def missing_host_key(self, client, hostname, key):
        raise UnknownHostKeyError(hostname, key)


class CWLedSFTPFileSystem(SFTPFileSystem):
    """
    fsspec SFTP filesystem that verifies host keys against known_hosts files.

    It loads the user's OpenSSH known_hosts and cwled's own file, then applies
    `_PromptForTrustPolicy`. Unknown keys are refused instead of being added.
    """

    def _connect(self):
        self.client = paramiko.SSHClient()
        if SYSTEM_KNOWN_HOSTS.exists():
            self.client.load_host_keys(str(SYSTEM_KNOWN_HOSTS))
        own = cwled_known_hosts_path()
        if own.exists():
            self.client.load_host_keys(str(own))
        self.client.set_missing_host_key_policy(_PromptForTrustPolicy())
        try:
            self.client.connect(self.host, **self.ssh_kwargs)
        except paramiko.BadHostKeyException as exc:
            self.client.close()
            raise HostKeyMismatchError(
                f"The host key for {self.host} changed. Refusing to connect."
            ) from exc
        except Exception:
            self.client.close()
            raise
        self.ftp = self.client.open_sftp()


fsspec.register_implementation('sftp', CWLedSFTPFileSystem, clobber=True)


@dataclass(frozen=True)
class SSHProfile:
    """
    Non-secret connection settings for one remote host.

    Attributes:
        name (str): label shown in the UI (the ssh config alias, or user-chosen).
        host (str): host name or IP address.
        username (str): remote user name.
        port (int): SSH port.
        key_path (str | None): private key file to authenticate with.
        proxy_command (str | None): ProxyCommand from ssh config, if any.
    """
    name: str
    host: str
    username: str
    port: int = DEFAULT_PORT
    key_path: Optional[str] = None
    proxy_command: Optional[str] = None

    @property
    def authority(self) -> str:
        """`user@host:port` as used in sftp:// URIs and as the session key."""
        return f"{self.username}@{self.host}:{self.port}"

    def to_dict(self) -> dict:
        """Serialise for cwled.yaml. Contains no secrets."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'SSHProfile':
        """Rebuild a profile saved by `to_dict`, ignoring unknown keys."""
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass(frozen=True)
class SSHConfigHost:
    """A concrete (non-wildcard) Host entry read from ~/.ssh/config."""
    alias: str
    hostname: str
    username: Optional[str]
    port: int
    identity_file: Optional[str]
    proxy_command: Optional[str]
    proxy_jump: Optional[str]

    def to_profile(self) -> SSHProfile:
        """
        Convert to a profile. Falls back to the local user name when ssh config has none.

        Raises:
            RemoteError: the entry uses ProxyJump, which is not supported.
        """
        if self.proxy_jump:
            raise RemoteError(f"Host {self.alias} uses ProxyJump, which is not supported. "
                              "Use a ProxyCommand entry instead.")
        return SSHProfile(
            name=self.alias,
            host=self.hostname,
            username=self.username or os.environ.get('USER', ''),
            port=self.port,
            key_path=self.identity_file,
            proxy_command=self.proxy_command,
        )


_ssh_config_cache: dict = {}


def _parsed_ssh_config(config_path: Path) -> Optional[paramiko.SSHConfig]:
    """
    Parse an OpenSSH config once per modification time. None if it cannot be read.

    Reopening the workspace dialog therefore does not re-parse the file.
    """
    try:
        mtime = config_path.stat().st_mtime
    except OSError:
        return None
    key = str(config_path)
    cached = _ssh_config_cache.get(key)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        ssh_config = paramiko.SSHConfig()
        with open(config_path, encoding='utf-8') as handle:
            ssh_config.parse(handle)
    except OSError as exc:  # unreadable config: offer no aliases rather than failing
        logger.warning(f"Could not read {config_path}: {exc}")
        return None
    _ssh_config_cache[key] = (mtime, ssh_config)
    return ssh_config


def list_ssh_config_aliases(config_path: Path = SSH_CONFIG_PATH) -> list[str]:
    """
    Concrete Host aliases in an OpenSSH config, sorted. Wildcard patterns are skipped.

    Only names are returned, so this stays fast however large the config is.
    """
    ssh_config = _parsed_ssh_config(config_path)
    if ssh_config is None:
        return []
    return sorted(alias for alias in ssh_config.get_hostnames()
                  if not any(ch in alias for ch in '*?!'))


def resolve_ssh_config_host(alias: str, config_path: Path = SSH_CONFIG_PATH) -> Optional[SSHConfigHost]:
    """
    Resolve the options of one alias. None if the config cannot be read.

    Args:
        alias (str): a Host alias from `list_ssh_config_aliases`.
        config_path (Path): the ssh config to read.
    """
    ssh_config = _parsed_ssh_config(config_path)
    if ssh_config is None:
        return None
    resolved = ssh_config.lookup(alias)
    identity = resolved.get('identityfile')
    return SSHConfigHost(
        alias=alias,
        hostname=resolved.get('hostname', alias),
        username=resolved.get('user'),
        port=int(resolved.get('port', DEFAULT_PORT)),
        identity_file=os.path.expanduser(identity[0]) if identity else None,
        proxy_command=resolved.get('proxycommand'),
        proxy_jump=resolved.get('proxyjump'),
    )


def list_ssh_config_hosts(config_path: Path = SSH_CONFIG_PATH) -> list[SSHConfigHost]:
    """
    Read every concrete Host alias with its options resolved.

    Resolving all aliases is slow for large configs; prefer `list_ssh_config_aliases`
    and `resolve_ssh_config_host` when only one host is needed.
    """
    hosts = []
    for alias in list_ssh_config_aliases(config_path):
        host = resolve_ssh_config_host(alias, config_path)
        if host is not None:
            hosts.append(host)
    return hosts


@dataclass
class _Session:
    """An open connection. `storage` holds the in-memory secrets for this session."""
    profile: SSHProfile
    storage: dict
    root: UPath


_sessions: dict[str, _Session] = {}


def _storage_options(profile: SSHProfile, password: Optional[str], passphrase: Optional[str]) -> dict:
    """Build the fsspec/paramiko keyword arguments for one profile."""
    options = {
        'host': profile.host,
        'port': profile.port,
        'username': profile.username,
        'look_for_keys': profile.key_path is None,
    }
    if profile.key_path:
        options['key_filename'] = os.path.expanduser(profile.key_path)
    if passphrase:
        options['passphrase'] = passphrase
    if password:
        options['password'] = password
    if profile.proxy_command:
        options['sock'] = paramiko.ProxyCommand(profile.proxy_command)
    return options


def trust_host_key(hostname: str, key: paramiko.PKey) -> None:
    """
    Record a host key the user has accepted in cwled's known_hosts file.

    Args:
        hostname (str): the name paramiko reported in `UnknownHostKeyError`.
        key (paramiko.PKey): the key that was shown to the user.
    """
    path = cwled_known_hosts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    host_keys = paramiko.HostKeys()
    if path.exists():
        host_keys.load(str(path))
    host_keys.add(hostname, key.get_name(), key)
    host_keys.save(str(path))
    logger.info(f"Trusted host key for {hostname}")


def connect(profile: SSHProfile,
            password: Optional[str] = None,
            passphrase: Optional[str] = None) -> UPath:
    """
    Open (or reuse) a connection and return the remote root.

    Args:
        profile (SSHProfile): where to connect.
        password (str, optional): password for password auth. Kept in memory only.
        passphrase (str, optional): passphrase for an encrypted key. Kept in memory only.

    Returns:
        UPath: the remote root directory (`sftp://user@host:port/`).

    Raises:
        UnknownHostKeyError: the host key is not trusted yet.
        HostKeyMismatchError: the host key changed.
        RemoteError: any other connection or authentication failure.
    """
    options = _storage_options(profile, password, passphrase)
    try:
        root = UPath(f"{URI_PREFIX}{profile.authority}/", **_without_host(options))
        # Touching the filesystem performs the connection and authentication.
        root.fs.ls('/', detail=False)
    except (UnknownHostKeyError, HostKeyMismatchError):
        raise
    except Exception as exc:
        logger.exception(f"Could not connect to {profile.authority}")
        raise RemoteError(f"Could not connect to {profile.authority}: {exc}") from exc
    _sessions[profile.authority] = _Session(profile=profile, storage=options, root=root)
    logger.info(f"Connected to {profile.authority}")
    return root


def _without_host(options: dict) -> dict:
    """UPath takes host, port and username from the URI, so drop them from storage options."""
    return {k: v for k, v in options.items() if k not in ('host', 'port', 'username')}


def disconnect(authority: str) -> None:
    """
    Close a session and forget its in-memory secrets.

    Args:
        authority (str): `user@host:port` of the session to close.
    """
    session = _sessions.pop(authority, None)
    if session is None:
        return
    session.storage.clear()
    fs = session.root.fs
    # fsspec keeps the connection arguments on the filesystem object, so scrub them too
    for secret in ('password', 'passphrase'):
        fs.ssh_kwargs.pop(secret, None)
    try:
        fs.client.close()
    except Exception:
        logger.debug(f"Closing the SSH client for {authority} failed", exc_info=True)
    logger.info(f"Disconnected from {authority}")


def is_remote(value) -> bool:
    """True for remote paths and sftp:// strings."""
    if isinstance(value, UPath):
        return True
    return isinstance(value, str) and value.startswith(URI_PREFIX)


def to_path(value: Union[str, Path, UPath]) -> Union[Path, UPath]:
    """
    Turn a location into the matching path type.

    Args:
        value: a local path, an sftp:// URI, or an existing path object.

    Returns:
        Path for local locations, UPath for remote ones.

    Raises:
        RemoteNotConnected: the URI's host has no open session.
    """
    if isinstance(value, (Path, UPath)):
        return value
    text = str(value)
    if not text.startswith(URI_PREFIX):
        return Path(text)
    # schema-salad identifiers carry #fragments (e.g. #main); they name no file
    text = text.split('#', 1)[0]
    authority = urlsplit(text).netloc
    session = _sessions.get(authority)
    if session is None:
        raise RemoteNotConnected(f"Not connected to {authority}. Open the remote workspace first.")
    return UPath(text, **_without_host(session.storage))


def to_uri(path: Union[str, Path, UPath]) -> str:
    """
    Return the canonical string for a location.

    UPath objects drop the host from `str()`, so remote paths are rebuilt
    from their connection details. Local paths return their string form.
    """
    if isinstance(path, UPath):
        fs = path.fs
        username = fs.ssh_kwargs.get('username', '')
        port = fs.ssh_kwargs.get('port', DEFAULT_PORT)
        return f"{URI_PREFIX}{username}@{fs.host}:{port}{path.path}"
    return str(path)


def session_for(value: Union[str, UPath]) -> Optional[_Session]:
    """The open session a remote location belongs to, or None for local paths."""
    if isinstance(value, UPath):
        return _sessions.get(urlsplit(to_uri(value)).netloc)
    if isinstance(value, str) and value.startswith(URI_PREFIX):
        return _sessions.get(urlsplit(value).netloc)
    return None


@dataclass(frozen=True)
class DirEntry:
    """One child of a directory, with what the browser needs from it."""
    path: Union[Path, UPath]
    is_dir: bool
    mtime: Optional[float]


def _timestamp(value) -> Optional[float]:
    """fsspec reports SFTP mtimes as datetimes; local stat reports floats."""
    if value is None:
        return None
    if hasattr(value, 'timestamp'):
        return value.timestamp()
    return float(value)


def list_entries(directory: Union[str, Path, UPath]) -> list[DirEntry]:
    """
    List a directory with type and mtime in one pass.

    For remote directories this uses a single fsspec `ls(detail=True)` call
    instead of separate stat calls per entry, which matters over SFTP.

    Args:
        directory: the directory to list.

    Returns:
        list[DirEntry]: the children, in server order.

    Raises:
        OSError: the directory cannot be read.
    """
    directory = to_path(directory)
    if isinstance(directory, UPath):
        entries = []
        for info in directory.fs.ls(directory.path, detail=True):
            name = posixpath.basename(info['name'].rstrip('/'))
            entries.append(DirEntry(
                path=directory / name,
                is_dir=info.get('type') == 'directory',
                mtime=_timestamp(info.get('mtime')),
            ))
        return entries
    entries = []
    for child in directory.iterdir():
        try:
            mtime = child.stat().st_mtime
        except OSError:  # e.g. a broken symlink should not hide its siblings
            mtime = None
        entries.append(DirEntry(path=child, is_dir=child.is_dir(), mtime=mtime))
    return entries


def display_path(value) -> str:
    """
    A readable label for a location, used in titles, menus and headers.

    Remote locations read as `remote - <server>: <path>`, where the server is the
    connection's profile name (e.g. the ssh config alias) or the host name.
    Local paths are returned unchanged. The sftp:// URI itself is kept for
    opening, saving and the recent-files list.
    """
    if not is_remote(value):
        return str(value)
    uri = to_uri(value)
    parts = urlsplit(uri)
    session = _sessions.get(parts.netloc)
    server = session.profile.name if session else parts.netloc.split('@', 1)[-1].rsplit(':', 1)[0]
    return f"remote - {server}: {parts.path or '/'}"


def is_inside(path: Union[str, Path, UPath], root: Union[str, Path, UPath, None]) -> bool:
    """
    Whether `path` lies within `root`. Works for local and remote locations.

    Local paths are compared after resolving symlinks. Remote paths are compared
    by their full URI, so a path on another host or user never matches.
    """
    if root is None:
        return False
    if is_remote(path) or is_remote(root):
        full = to_uri(path)
        base = to_uri(root).rstrip('/')
        return full == base or full.startswith(base + '/')
    return Path(path).resolve().is_relative_to(Path(root).resolve())


def canonical(path: Union[str, Path, UPath]) -> str:
    """
    A stable key for a location, used to compare paths the app has seen.

    Local paths resolve symlinks; remote paths use their full URI.
    """
    if is_remote(path):
        return to_uri(to_path(path))
    return str(Path(path).resolve())


def join_location(base_dir: Union[str, Path, UPath], reference: str) -> str:
    """
    Resolve a `run:`-style reference against a document folder.

    Returns:
        str: an absolute local path, or an sftp:// URI when `base_dir` is remote.
    """
    if is_remote(base_dir):
        # base_dir is a folder, so the reference is joined onto it directly
        if urlsplit(reference).scheme:
            return reference
        parts = urlsplit(to_uri(base_dir))
        joined = reference if reference.startswith('/') else posixpath.join(parts.path, reference)
        return f"{URI_PREFIX}{parts.netloc}{posixpath.normpath(joined)}"
    return str(Path(base_dir, reference).absolute())


def absolute(path: Union[Path, UPath]) -> Union[Path, UPath]:
    """`Path.absolute()` for local paths. Remote paths are already absolute."""
    return path if isinstance(path, UPath) else path.absolute()


def posix_path(path: Union[str, Path, UPath]) -> str:
    """The POSIX-style location used for relative path arithmetic."""
    if isinstance(path, UPath):
        return path.path
    return str(path)


def normalise_remote_join(base: str, relative: str) -> str:
    """
    Join a relative reference onto an sftp:// base, the way schema-salad needs.

    `urllib.parse.urljoin` does not know sftp, so it returns the relative part
    unchanged. This function joins using POSIX rules and keeps the authority.
    """
    base_parts = urlsplit(base)
    if urlsplit(relative).scheme:
        return relative
    if relative.startswith('/'):
        joined = relative
    else:
        joined = posixpath.join(posixpath.dirname(base_parts.path), relative)
    return f"{URI_PREFIX}{base_parts.netloc}{posixpath.normpath(joined)}"


# Fields of a CWL document that name another file which cwltool will need
REFERENCE_KEYS = ('run', '$import', '$include')


def _references(node) -> Iterator[str]:
    """Yield every file reference (run, $import, $include) found in a loaded CWL document."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in REFERENCE_KEYS and isinstance(value, str):
                yield value.split('#', 1)[0]
            else:
                yield from _references(value)
    elif isinstance(node, list):
        for item in node:
            yield from _references(item)


def mirror_document(document: Union[str, Path, UPath], workdir: Path) -> Path:
    """
    Copy a remote CWL document and the files it references into a local folder.

    The folder layout matches the server folder the document lives in, so the
    relative `run:` and `$import` references still resolve for cwltool.

    Args:
        document: sftp:// location of the document.
        workdir (Path): empty local folder to copy into.

    Returns:
        Path: the local copy of the document.

    Raises:
        RemoteError: a reference points outside the document's folder, which
            cannot be mirrored while keeping the layout.
    """
    from ruamel.yaml import YAML
    import json

    root = to_path(document)
    root_dir = posix_path(root.parent)
    yaml = YAML(typ='safe')
    queue = [root]
    seen = {to_uri(root)}
    local_root = None
    while queue:
        current = queue.pop()
        text = current.read_text(encoding='utf-8')
        relative = posixpath.relpath(posix_path(current), root_dir)
        if relative.startswith('..'):
            raise RemoteError(f"{to_uri(current)} is outside the workflow folder and cannot be checked locally")
        local = workdir / relative
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(text, encoding='utf-8')
        if local_root is None:
            local_root = local
        try:
            loaded = json.loads(text) if text.lstrip().startswith('{') else yaml.load(text)
        except Exception:
            logger.debug(f"Could not parse {to_uri(current)} for references", exc_info=True)
            continue
        for reference in _references(loaded or {}):
            if urlsplit(reference).scheme:
                continue  # http(s) and other absolute identifiers are not copied
            target_uri = normalise_remote_join(to_uri(current), reference)
            if target_uri in seen:
                continue
            seen.add(target_uri)
            queue.append(to_path(target_uri))
    logger.info(f"Mirrored {len(seen)} file(s) of {to_uri(root)} into {workdir}")
    return local_root


@contextlib.contextmanager
def mirrored(document: Union[str, Path, UPath]) -> Iterator[Path]:
    """
    Mirror a remote document into a temporary local folder for the duration of a block.

    Yields:
        Path: the local copy of the document. The folder is deleted on exit.
    """
    workdir = Path(tempfile.mkdtemp(prefix='cwled-remote-'))
    try:
        yield mirror_document(document, workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def replace_file(temp: UPath, target: UPath) -> None:
    """
    Move a finished remote file over `target`.

    Uses the SFTP posix-rename extension, which replaces the target in one step,
    where the server supports it. Otherwise the old file is removed and the new
    one renamed into place (a short window with no file).

    Args:
        temp (UPath): the complete new content.
        target (UPath): the file to replace.
    """
    try:
        temp.fs.ftp.posix_rename(temp.path, target.path)
        return
    except Exception as exc:
        logger.debug(f"posix-rename unavailable, falling back to remove and rename: {exc}")
    if target.exists():
        target.unlink()
    # plain SFTP rename: fsspec's mv would retry the posix-rename extension first
    temp.fs.ftp.rename(temp.path, target.path)


def publish(local_file: Path, destination: Union[str, Path, UPath]) -> None:
    """
    Copy a local file (e.g. tool output) to a remote location, overwriting it.

    Args:
        local_file (Path): the file produced locally.
        destination: sftp:// location to write.
    """
    target = to_path(destination)
    with target.open('wb') as out, open(local_file, 'rb') as src:
        shutil.copyfileobj(src, out)
    logger.info(f"Published {local_file} to {to_uri(target)}")
