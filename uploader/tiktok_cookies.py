import os

from uploader.base import PostResult, Uploader

_COOKIE_HELP = (
    "export cookies while logged into that account: install a 'Get cookies.txt "
    "LOCALLY' browser extension, open tiktok.com, export, save as {path}")


class CookieUploader(Uploader):
    """tiktok-uploader (browser cookies) implementation.

    ToS-gray — see the README risk note. Swapped for the official API
    implementation once the app audit is approved."""

    def __init__(self, cookies_file: str, account: str):
        if not os.path.exists(cookies_file):
            raise RuntimeError(
                f"cookies file {cookies_file} for account '{account}' not "
                "found — " + _COOKIE_HELP.format(path=cookies_file))
        self.cookies_file = cookies_file
        self.account = account

    def upload(self, video_path: str, caption: str) -> PostResult:
        # lazy import: selenium only loads when a real upload happens
        from tiktok_uploader.upload import upload_video
        try:
            failed = upload_video(video_path, description=caption,
                                  cookies=self.cookies_file)
        except Exception as exc:
            return PostResult(False, f"{exc.__class__.__name__}: {exc}")
        if failed:
            return PostResult(False, f"tiktok-uploader reported failure: {failed}")
        return PostResult(True, "uploaded")
