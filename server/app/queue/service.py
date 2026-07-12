from collections.abc import Callable
from datetime import timedelta

class JobError(Exception):
    def __init__(self, safe_code: str) -> None:
        super().__init__(safe_code); self.safe_code = safe_code
class RetryableJobError(JobError): pass
class PermanentJobError(JobError): pass

def retry_delay(attempt: int, *, base_seconds: int = 5, maximum_seconds: int = 300, jitter: Callable[[int], int]) -> timedelta:
    seconds = base_seconds * 2 ** max(0, attempt - 1) + jitter(attempt)
    return timedelta(seconds=min(maximum_seconds, max(0, seconds)))
