from types import SimpleNamespace

import config
import main
from uploader.base import PostResult
from post_log import read_posts


def story():
    return SimpleNamespace(id="s1", title="A tale", url="u", niche="drama")


def redirect_paths(tmp_path, monkeypatch, with_video=True):
    monkeypatch.setattr(config, "POST_LOG_PATH", str(tmp_path / "posts.jsonl"))
    monkeypatch.setattr(config, "OUTBOX_DIR", str(tmp_path / "outbox"))
    monkeypatch.setattr(config, "OUTPUT_VID_PATH", str(tmp_path / "out.mp4"))
    if with_video:
        (tmp_path / "out.mp4").write_bytes(b"video")


class FakeUploader:
    def __init__(self, result):
        self.result = result

    def upload(self, video_path, caption):
        return self.result


def test_dry_run_logs_and_never_uploads(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch, with_video=False)
    monkeypatch.setattr(
        main, "CookieUploader",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("constructed")))
    assert main._publish(story(), "drama_main", dry_run=True) == 0
    posts = read_posts(config.POST_LOG_PATH)
    assert posts[0]["ok"] is None and posts[0]["story_id"] == "s1"


def test_success_logs_and_keeps_video(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "CookieUploader",
                        lambda *a, **kw: FakeUploader(PostResult(True, "uploaded")))
    assert main._publish(story(), "drama_main", dry_run=False) == 0
    assert read_posts(config.POST_LOG_PATH)[0]["ok"] is True
    assert (tmp_path / "out.mp4").exists()


def test_failure_parks_video_in_outbox(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "CookieUploader",
                        lambda *a, **kw: FakeUploader(PostResult(False, "boom")))
    assert main._publish(story(), "drama_main", dry_run=False) == 1
    assert not (tmp_path / "out.mp4").exists()
    assert (tmp_path / "outbox" / "s1.mp4").read_bytes() == b"video"
    caption = (tmp_path / "outbox" / "s1.txt").read_text(encoding="utf-8")
    assert caption.startswith("A tale")
    assert read_posts(config.POST_LOG_PATH)[0]["ok"] is False
