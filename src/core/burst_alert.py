"""A counter that turns "this keeps happening" into ONE error line (an alert), per process.

``answer_not_checked`` is a warning for each single answer; five in ten minutes means the symbolic checker is down or
overloaded (students are being asked to resend answers), which somebody has to look at.  The clock is injectable, so
tests never read the real time.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Deque


class BurstAlert:
    def __init__(self, *, threshold: int, window_s: float, clock: Callable[[], float] = time.monotonic):
        self.threshold, self.window_s, self._clock = threshold, window_s, clock
        self._events: Deque[float] = deque()
        self._lock = threading.Lock()

    def hit(self) -> int:
        """Record one event.  Returns the number of events in the window when it reaches the threshold (and starts a
        new count, so the line is not repeated for every further event), otherwise 0."""
        now = self._clock()
        with self._lock:
            self._events.append(now)
            while self._events and now - self._events[0] > self.window_s:
                self._events.popleft()
            if len(self._events) >= self.threshold:
                count = len(self._events)
                self._events.clear()
                return count
            return 0
