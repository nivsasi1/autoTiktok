import os
from contextlib import contextmanager, suppress


@contextmanager
def atomic_path(final_path: str):
    """Yield a temp sibling path; promote it to final_path only on success.

    A failure anywhere (write, validation, even the replace itself) removes
    the temp, so callers never leave partial files that could be mistaken
    for good ones. The PID keeps overlapping runs off each other's temp.
    """
    tmp = f"{final_path}.{os.getpid()}.tmp"
    try:
        yield tmp
        os.replace(tmp, final_path)
    finally:
        with suppress(OSError):
            os.unlink(tmp)   # no-op after a successful replace
