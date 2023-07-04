# Source: https://gist.github.com/timofurrer/db44ad05ffffd74f73384e2eb0bfb682

import queue
import threading


class PriorityLock:
    class _Context:
        def __init__(self, lock, priority):
            self._lock = lock
            self._priority = priority

        def __enter__(self):
            self._lock.acquire(self._priority)

        def __exit__(self, exc_type, exc_val, exc_tb):
            self._lock.release()

    def __init__(self):
        self._lock = threading.Lock()
        self._acquire_queue = queue.PriorityQueue()
        self._need_to_wait = False

    def acquire(self, priority):
        with self._lock:
            if not self._need_to_wait:
                self._need_to_wait = True
                return True

            event = threading.Event()
            self._acquire_queue.put((priority, event))
        event.wait()
        return True

    def release(self):
        with self._lock:
            try:
                _, event = self._acquire_queue.get_nowait()
            except queue.Empty:
                self._need_to_wait = False
            else:
                event.set()

    def __call__(self, priority):
        return self._Context(self, priority)
