"""
Shared schema-salad fetcher used by every CWL parse in CWLed.

CWL documents routinely declare `$namespaces` prefixes that do not end in `/`
or `#`. Seven Bridges exports, for instance, declare
`sbg: 'https://sevenbridges.com'`, so schema-salad expands `sbg:SaveLogs` into
the absolute URI `https://sevenbridges.comSaveLogs`. That URI is not in the CWL
vocabulary, so schema-salad link-checks it with an HTTPS HEAD request - about
44 requests per step file, once per union branch it tries. The host does not
resolve, the negative result is never cached, and the graph is rebuilt on every
tab switch, so loading a workflow stalls on DNS timeouts.

CWLed does not need remote identifiers to resolve: link checking is only useful
for the local step files, and real validation is delegated to
`cwltool --validate`. This fetcher therefore accepts remote identifiers without
a request, while `$schemas` are still fetched (and cached) through `fetch_text`.
"""

import logging
import os
import tempfile
from pathlib import Path

from schema_salad.fetcher import DefaultFetcher

import remote

logger = logging.getLogger(__name__)

REMOTE_SCHEMES = ('http://', 'https://')


class CWLedFetcher(DefaultFetcher):
    """
    A DefaultFetcher that resolves remote identifiers without network access.

    Only `check_exists` is overridden; `fetch_text` still retrieves `$schemas`
    and remote `run:` targets so documents that genuinely point at a URL keep
    working.
    """

    def check_exists(self, url: str) -> bool:
        """
        Report whether the resource exists, without probing remote hosts.

        Args:
            url (str): the absolute URI schema-salad wants to link-check.

        Returns:
            bool: True for any http(s) URI, the SFTP answer for sftp:// URIs,
                otherwise the DefaultFetcher answer.
        """
        if url.startswith(REMOTE_SCHEMES):
            logger.debug(f"Accepting remote identifier without a link check: {url}")
            return True
        if remote.is_remote(url):
            try:
                return remote.to_path(url).is_file()
            except remote.RemoteError:
                return False
        return super().check_exists(url)

    def fetch_text(self, url: str, content_types: list[str] | None = None) -> str:
        """
        Read a CWL document or `$schemas` entry. sftp:// URIs are read over SFTP.

        Args:
            url (str): the URI to read.
            content_types (list[str], optional): HTTP Accept types, unused for SFTP.

        Returns:
            str: the document text.
        """
        if remote.is_remote(url):
            return remote.to_path(url).read_text(encoding='utf-8')
        return super().fetch_text(url, content_types)

    def urljoin(self, base_url: str, url: str) -> str:
        """
        Resolve a reference against its document. Remote bases use POSIX joining.

        Args:
            base_url (str): URI of the document the reference appears in.
            url (str): the reference, relative or absolute.

        Returns:
            str: the resolved URI.
        """
        if remote.is_remote(base_url) and not url.startswith('_:'):
            return remote.normalise_remote_join(base_url, url)
        return super().urljoin(base_url, url)


# Process-wide state. The cache only ever holds successful `check_exists`
# results and parsed `$schemas` graphs (schema-salad never caches document
# text), so sharing it across parses cannot serve stale file content - it just
# stops every parse from re-downloading the same extension schemas.
_cache = {}
_fetcher = None


def getFetcher() -> CWLedFetcher:
    """
    Return the process-wide fetcher, creating it on first use.

    Returns:
        CWLedFetcher: fetcher backed by an on-disk HTTP cache under ~/.cache/salad.
    """
    global _fetcher
    if _fetcher is None:
        import data
        logger.setLevel(data.configuration.get('logLevel', {}).get(__name__, 'WARNING'))

        import requests
        from cachecontrol.caches import SeparateBodyFileCache
        from cachecontrol.wrapper import CacheControl

        root = Path(os.environ.get('HOME', tempfile.gettempdir()))
        session = CacheControl(
            requests.Session(),
            cache=SeparateBodyFileCache(root / '.cache' / 'salad')
        )
        _fetcher = CWLedFetcher(_cache, session)
        logger.debug("Created the shared CWLed schema-salad fetcher")
    return _fetcher
