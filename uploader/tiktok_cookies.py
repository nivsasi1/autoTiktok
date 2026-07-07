import logging
import os

from uploader.base import PostResult, Uploader

_COOKIE_HELP = (
    "export cookies while logged into that account: install a 'Get cookies.txt "
    "LOCALLY' browser extension, open tiktok.com, export, save as {path}")


def missing_cookies_error(cookies_file: str, account: str) -> str:
    """Name the exact problem, and any near-miss .txt sitting in the folder
    (a one-letter filename typo once cost a whole debugging round)."""
    msg = (f"cookies file {cookies_file} for account '{account}' not found — "
           + _COOKIE_HELP.format(path=cookies_file))
    folder = os.path.dirname(cookies_file) or "."
    try:
        others = sorted(n for n in os.listdir(folder) if n.endswith(".txt"))
    except OSError:
        others = []
    if others:
        msg += (f". The folder does contain: {', '.join(others)} — "
                "a typo in the filename?")
    return msg


class CookieUploader(Uploader):
    """tiktok-uploader (browser cookies) implementation.

    ToS-gray — see the README risk note. Swapped for the official API
    implementation once the app audit is approved."""

    def __init__(self, cookies_file: str, account: str):
        if not os.path.exists(cookies_file):
            raise RuntimeError(missing_cookies_error(cookies_file, account))
        self.cookies_file = cookies_file
        self.account = account

    def upload(self, video_path: str, caption: str) -> PostResult:
        # tiktok-uploader swallows the real failure reason into its logger
        # (any exception -> logger.error -> video appended to the failed
        # list); tap that logger so our PostResult can say WHY
        records = []
        handler = logging.Handler()
        handler.emit = lambda r: records.append((r.levelno, r.getMessage()))
        lib_logger = logging.getLogger("tiktok_uploader")
        prev_level = lib_logger.level
        lib_logger.addHandler(handler)
        lib_logger.setLevel(logging.DEBUG)
        try:
            # lazy import: playwright only loads when a real upload happens
            from tiktok_uploader.upload import upload_video
            failed = upload_video(video_path, description=caption,
                                  cookies=self.cookies_file)
        except Exception as exc:
            return PostResult(False, f"{exc.__class__.__name__}: {exc}")
        finally:
            lib_logger.removeHandler(handler)
            lib_logger.setLevel(prev_level)
        if failed:
            errors = [m for lvl, m in records if lvl >= logging.ERROR]
            tail = " | ".join(errors[-3:] if errors
                              else [m for _, m in records[-3:]])
            return PostResult(False, "tiktok-uploader reported failure: "
                                     f"{tail or failed}")
        return PostResult(True, "uploaded")
