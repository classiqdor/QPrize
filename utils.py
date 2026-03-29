import subprocess
import threading
import time


class timed:
    """Context manager that prints elapsed time every `interval` seconds, then total on exit.

    Usage:
        with timed("Synthesizing"):
            qprog = synthesize(qmod)
    """
    def __init__(self, label: str, interval: int = 10):
        self.label = label
        self.interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._tick, daemon=True)

    def _tick(self):
        start = time.time()
        while not self._stop.wait(self.interval):
            print(f"  [{self.label}] {time.time() - start:.0f}s...", flush=True)

    def __enter__(self):
        self._start = time.time()
        print(f"[{self.label}] starting...", flush=True)
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()
        print(f"[{self.label}] done in {time.time() - self._start:.1f}s", flush=True)


def play_ending_sound():
    subprocess.Popen(["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"])
