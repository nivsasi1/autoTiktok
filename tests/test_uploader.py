import sys
from types import SimpleNamespace

import pytest

from uploader.base import PostResult, Uploader
from uploader.tiktok_cookies import CookieUploader


def make_uploader(tmp_path):
    cookies = tmp_path / "acct.txt"
    cookies.write_text("# netscape cookies", encoding="utf-8")
    return CookieUploader(str(cookies), "acct")


def fake_lib(monkeypatch, upload_video):
    mod = SimpleNamespace(upload_video=upload_video)
    monkeypatch.setitem(sys.modules, "tiktok_uploader", SimpleNamespace(upload=mod))
    monkeypatch.setitem(sys.modules, "tiktok_uploader.upload", mod)


def test_missing_cookies_raise_named_error(tmp_path):
    with pytest.raises(RuntimeError, match=r"acct.*not found|not found.*acct"):
        CookieUploader(str(tmp_path / "missing.txt"), "acct")


def test_upload_success(tmp_path, monkeypatch):
    up = make_uploader(tmp_path)
    fake_lib(monkeypatch, lambda *a, **kw: [])
    result = up.upload("out.mp4", "caption")
    assert result == PostResult(True, "uploaded")


def test_upload_reported_failure(tmp_path, monkeypatch):
    up = make_uploader(tmp_path)
    fake_lib(monkeypatch, lambda *a, **kw: ["out.mp4"])
    result = up.upload("out.mp4", "caption")
    assert result.ok is False
    assert "failure" in result.detail


def test_upload_exception_becomes_result(tmp_path, monkeypatch):
    up = make_uploader(tmp_path)

    def boom(*a, **kw):
        raise TimeoutError("browser died")

    fake_lib(monkeypatch, boom)
    result = up.upload("out.mp4", "caption")
    assert result.ok is False
    assert "TimeoutError" in result.detail


def test_uploader_is_abstract():
    with pytest.raises(TypeError):
        Uploader()


def test_upload_import_failure_becomes_result(tmp_path, monkeypatch):
    up = make_uploader(tmp_path)
    monkeypatch.setitem(sys.modules, "tiktok_uploader", None)
    monkeypatch.setitem(sys.modules, "tiktok_uploader.upload", None)
    result = up.upload("out.mp4", "caption")
    assert result.ok is False
