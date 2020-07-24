import threading

from typing import Optional

# This class only exists because "threading.Thread" does not offer any
# programmatic indication of whether the thread hit an exception.
class Thread(threading.Thread):

    exception: Optional[Exception] = None

    def run(self) -> None:
        try:
            super().run()
        except Exception as e:
            self.exception = e
            raise

    def join(self, timeout: Optional[float] = None) -> None:
        super().join(timeout=timeout)

        if self.exception:
            raise self.exception
