"""Persistent-profile TikTok uploader.

Cookie-file replay bounces to the login page: TikTok binds web sessions to
device keys in the original browser's storage (ticket guard), which a
cookies.txt export can't carry. So uploads run inside a persistent Chrome
profile the user logged into ONCE via `python main.py --login --account X`;
cookies, storage and device keys all live in the profile dir and stay valid.
Reuses tiktok-uploader's maintained upload-form driver on top.
"""

import os
import shutil
import sqlite3
import tempfile
import time

from uploader.base import PostResult, Uploader

_CHROME_EPOCH_OFFSET_S = 11644473600   # Chrome stamps µs since 1601-01-01


def find_chrome():
    """Path to the real chrome.exe, or None. Login must run in a PLAIN
    Chrome: Google blocks OAuth inside automation-controlled browsers."""
    roots = [os.environ.get("ProgramFiles", r"C:\Program Files"),
             os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
             os.environ.get("LOCALAPPDATA", "")]
    for root in roots:
        candidate = os.path.join(root, "Google", "Chrome", "Application",
                                 "chrome.exe")
        if root and os.path.exists(candidate):
            return candidate
    return None


def profile_logged_in(profile_dir) -> bool:
    """True if the profile's cookie DB holds an unexpired TikTok sessionid.
    Reads a COPY of the SQLite file (Chrome locks the live one). Values are
    encrypted but names/domains/expiries aren't — enough for a status check."""
    for rel in (("Default", "Network", "Cookies"), ("Default", "Cookies")):
        db = os.path.join(profile_dir, *rel)
        if os.path.exists(db):
            break
    else:
        return False
    try:
        with tempfile.TemporaryDirectory() as td:
            tmp = os.path.join(td, "Cookies")
            shutil.copy2(db, tmp)
            con = sqlite3.connect(tmp)
            try:
                row = con.execute(
                    "SELECT expires_utc FROM cookies WHERE name='sessionid' "
                    "AND host_key LIKE '%tiktok.com' "
                    "ORDER BY expires_utc DESC LIMIT 1").fetchone()
            finally:
                con.close()
    except Exception:
        return False
    if not row:
        return False
    return row[0] / 1_000_000 - _CHROME_EPOCH_OFFSET_S > time.time()


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
