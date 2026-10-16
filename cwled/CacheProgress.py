"""
A progress box shown while remote files are copied into the local cache.

It appears when the cache has to talk to the server (checking or downloading) and
takes longer than half a second, and disappears when the caching is finished.
Caching cannot be cancelled part way, so the box has no cancel button.
"""

import contextlib
import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QProgressDialog, QWidget

import remote_cache

logger = logging.getLogger(__name__)


class _CacheProgressBox:
    """Receives progress from remote_cache and drives a QProgressDialog."""

    def __init__(self, parent: Optional[QWidget], location: str):
        self._parent = parent
        self._location = location
        self._dialog: Optional[QProgressDialog] = None

    def __call__(self, done: int, total: int, name: str, contacted: bool) -> None:
        if not contacted:
            return
        if self._dialog is None:
            self._dialog = QProgressDialog(self._parent)
            self._dialog.setWindowTitle("Caching remote files")
            self._dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            self._dialog.setCancelButton(None)
            # shown only if caching is still going after half a second
            self._dialog.setMinimumDuration(500)
            self._dialog.setAutoClose(False)
            self._dialog.setAutoReset(False)
            self._dialog.setMinimumWidth(420)
        self._dialog.setLabelText(f"Updating the local copy of {self._location}...\n{name}")
        self._dialog.setMaximum(max(total, 1))
        self._dialog.setValue(done)
        QApplication.processEvents()

    def close(self) -> None:
        if self._dialog is not None:
            self._dialog.close()
            self._dialog = None


@contextlib.contextmanager
def caching_progress(parent: Optional[QWidget], location: str):
    """
    Show a progress box while the block copies remote files into the cache.

    Args:
        parent (QWidget, optional): window the box belongs to.
        location (str): readable name of the document being cached.
    """
    box = _CacheProgressBox(parent, location)
    try:
        with remote_cache.progress_listener(box):
            yield
    finally:
        box.close()
