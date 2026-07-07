"""Persistent-profile TikTok uploader.

Cookie-file replay bounces to the login page: TikTok binds web sessions to
device keys in the original browser's storage (ticket guard), which a
cookies.txt export can't carry. So uploads run inside a persistent Chrome
profile the user logged into ONCE via `python main.py --login --account X`;
cookies, storage and device keys all live in the profile dir and stay valid.
Reuses tiktok-uploader's maintained upload-form driver on top.
"""

import os

from uploader.base import PostResult, Uploader


class ProfileUploader(Uploader):
    def __init__(self, profile_dir: str, account: str):
        self.profile_dir = profile_dir
        self.account = account

    def _login_hint(self) -> str:
        return (f"profile for '{self.account}' isn't logged in — run: "
                f"python main.py --login --account {self.account}")

    def upload(self, video_path: str, caption: str) -> PostResult:
        try:
            # lazy imports: playwright only loads when a real upload happens
            from playwright.sync_api import sync_playwright
            from tiktok_uploader import config as tt_config
            from tiktok_uploader.upload import complete_upload_form
        except Exception as exc:
            return PostResult(False, f"{exc.__class__.__name__}: {exc}")
        try:
            with sync_playwright() as p:
                ctx = p.chromium.launch_persistent_context(
                    self.profile_dir, channel="chrome", headless=False)
                try:
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    page.goto(str(tt_config.paths.main))
                    page.wait_for_load_state()
                    if "login" in page.url or "explore" in page.url:
                        return PostResult(False, self._login_hint())
                    complete_upload_form(page, os.path.abspath(video_path),
                                         caption, schedule=None,
                                         skip_split_window=False)
                finally:
                    ctx.close()
        except Exception as exc:
            return PostResult(False, f"{exc.__class__.__name__}: {exc}")
        return PostResult(True, "uploaded")
