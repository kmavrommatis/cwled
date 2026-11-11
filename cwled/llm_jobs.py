"""
Runs LLM requests off the GUI thread.

A request runs in a daemon thread. Its reply comes back to the GUI thread through the `done` signal,
which Qt delivers in the event loop of the object that owns the LLMJob.

The function passed to `start` runs in the background, so it must not touch Qt objects or the
CWL document. Everything it needs is prepared on the GUI thread before the job starts.
"""

import logging
import threading
from typing import Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal


class LLMJob(QObject):
    """
    Runs one LLM request at a time in the background.

    Every start gets a token. A reply is only meaningful if its token is still current,
    so `cancel` makes any reply still in flight stale.
    """
    done = pyqtSignal(object, object, str)  # token, reply text (None on error), error message ('' when none)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(self.__class__.__name__)
        self._lock = threading.Lock()
        self._current = 0               # token of the latest start or cancel
        self._active: Optional[int] = None  # token of the request still waiting for its reply

    def start(self, request: Callable[[], str]) -> int:
        """Run `request` in the background and return its token."""
        with self._lock:
            self._current += 1
            token = self._current
            self._active = token
        self.logger.debug(f"Starting background LLM request {token}")
        threading.Thread(target=self._run, args=(token, request), daemon=True).start()
        return token

    def isBusy(self) -> bool:
        """True while a request has been started and its reply has not been handled yet."""
        return self._active is not None

    def isCurrent(self, token: int) -> bool:
        """True if the reply for `token` should still be used."""
        return token == self._current

    def finish(self, token: int) -> None:
        """Mark the reply for `token` as handled."""
        if token == self._active:
            self._active = None

    def cancel(self) -> None:
        """Drop the request in flight. Its reply, when it arrives, is ignored."""
        with self._lock:
            self._current += 1
            self._active = None

    def _run(self, token: int, request: Callable[[], str]) -> None:
        try:
            text, error = request(), ''
        except Exception as e:
            self.logger.exception(f"Background LLM request {token} failed")
            text, error = None, str(e) or type(e).__name__
        try:
            self.done.emit(token, text, error)
        except RuntimeError:
            # the owner was deleted while the request was running
            self.logger.debug(f"Reply for request {token} dropped: owner no longer exists")
