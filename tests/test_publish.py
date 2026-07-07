import re
import sys
from types import SimpleNamespace

import config
import main
import pending
from uploader.base import PostResult
from post_log import read_posts


def story():
    return SimpleNamespace(id="s1", title="A tale", url="u", niche="drama")


def redirect_paths(tmp_path, monkeypatch, with_video=True):
    monkeypatch.setattr(config, "POST_LOG_PATH", str(tmp_path / "posts.jsonl"))
    monkeypatch.setattr(config, "OUTBOX_DIR", str(tmp_path / "outbox"))
    monkeypatch.setattr(config, "OUTPUT_VID_PATH", str(tmp_path / "out.mp4"))
    # never let a REAL queued part 2 leak into a test run
    monkeypatch.setattr(config, "QUEUE_DIR", str(tmp_path / "queue"))
    # nor a real logged-in browser profile (would bypass the fake uploader)
    monkeypatch.setattr(config, "PROFILES_DIR", str(tmp_path / "profiles"))
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
    assert main._publish(story(), "redditregrets", dry_run=True) == 0
    posts = read_posts(config.POST_LOG_PATH)
    assert posts[0]["ok"] is None and posts[0]["story_id"] == "s1"
    # url is logged so a parked post can be traced back to its thread by hand
    assert posts[0]["url"] == "u"
    # ts carries a utc offset so it stays unambiguous across DST
    assert re.search(r"[+-]\d{4}$", posts[0]["ts"])


def test_success_logs_and_keeps_video(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "CookieUploader",
                        lambda *a, **kw: FakeUploader(PostResult(True, "uploaded")))
    assert main._publish(story(), "redditregrets", dry_run=False) == 0
    assert read_posts(config.POST_LOG_PATH)[0]["ok"] is True
    assert (tmp_path / "out.mp4").exists()


def test_failure_parks_video_in_outbox(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "CookieUploader",
                        lambda *a, **kw: FakeUploader(PostResult(False, "boom")))
    assert main._publish(story(), "redditregrets", dry_run=False) == 1
    assert not (tmp_path / "out.mp4").exists()
    assert (tmp_path / "outbox" / "s1.mp4").read_bytes() == b"video"
    caption = (tmp_path / "outbox" / "s1.txt").read_text(encoding="utf-8")
    assert caption.startswith("A tale")
    assert read_posts(config.POST_LOG_PATH)[0]["ok"] is False


def test_missing_cookies_parks_video_not_crash(tmp_path, monkeypatch):
    # finding #1: if the cookies file vanishes between the pre-check and _publish,
    # CookieUploader's constructor raises — that must park the rendered video in
    # the outbox (like any upload failure), not crash and strand it
    redirect_paths(tmp_path, monkeypatch)

    def boom(*a, **kw):
        raise RuntimeError("cookies file cookies/x.txt for 'x' not found")

    monkeypatch.setattr(main, "CookieUploader", boom)
    assert main._publish(story(), "redditregrets", dry_run=False) == 1
    assert not (tmp_path / "out.mp4").exists()
    assert (tmp_path / "outbox" / "s1.mp4").read_bytes() == b"video"
    rec = read_posts(config.POST_LOG_PATH)[0]
    assert rec["ok"] is False and "RuntimeError" in rec["detail"]


def queue_part2(tmp_path, monkeypatch, account="redditregrets"):
    monkeypatch.setattr(config, "QUEUE_DIR", str(tmp_path / "queue"))
    src = tmp_path / "part2.mp4"
    src.write_bytes(b"part2")
    return pending.enqueue(config.QUEUE_DIR, str(src),
                           {"story_id": "s1", "part": 2, "account": account,
                            "niche": "drama", "title": "A tale", "url": "u",
                            "caption": "A tale (Part 2/2) #x"})


def test_queued_part_posts_before_fetching_anything(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch, with_video=False)
    queue_part2(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "CookieUploader",
                        lambda *a, **kw: FakeUploader(PostResult(True, "up")))
    # cookies pre-check must pass for a live post
    cookies = tmp_path / "c.txt"
    cookies.write_text("k=v", encoding="utf-8")
    monkeypatch.setattr(config.ACCOUNTS["redditregrets"], "cookies_file",
                        str(cookies))
    monkeypatch.setattr(
        main, "build_source",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("fetched")))
    monkeypatch.setattr(config, "POST_JITTER_MAX_S", 0)
    monkeypatch.setattr(
        sys, "argv", ["main.py", "--post", "--account", "redditregrets"])
    assert main.main() == 0
    rec = read_posts(config.POST_LOG_PATH)[0]
    assert rec["ok"] is True and rec["part"] == 2 and rec["story_id"] == "s1"
    # entry consumed: queue is empty afterwards
    assert pending.next_entry(config.QUEUE_DIR, "redditregrets") is None


def test_dry_run_reports_queued_part_but_keeps_it(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch, with_video=False)
    queue_part2(tmp_path, monkeypatch)
    monkeypatch.setattr(
        main, "CookieUploader",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("constructed")))
    monkeypatch.setattr(
        sys, "argv",
        ["main.py", "--post", "--account", "redditregrets", "--dry-run"])
    assert main.main() == 0
    rec = read_posts(config.POST_LOG_PATH)[0]
    assert rec["ok"] is None and rec["part"] == 2
    # still queued for the real run
    assert pending.next_entry(config.QUEUE_DIR, "redditregrets") is not None


def test_failed_queued_part_parks_with_part_suffix(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch, with_video=False)
    qvideo = queue_part2(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "CookieUploader",
                        lambda *a, **kw: FakeUploader(PostResult(False, "boom")))
    story_ns = SimpleNamespace(id="s1", title="A tale", url="u")
    assert main._publish(story_ns, "redditregrets", dry_run=False, part=2,
                         video_path=qvideo, caption="cap") == 1
    assert (tmp_path / "outbox" / "s1_p2.mp4").read_bytes() == b"part2"
    assert (tmp_path / "outbox" / "s1_p2.txt").read_text(encoding="utf-8") == "cap"


def test_uploader_prefers_logged_in_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILES_DIR", str(tmp_path / "profiles"))
    # no profile dir -> cookies-file uploader (may raise on missing file)
    monkeypatch.setattr(main, "CookieUploader",
                        lambda *a, **kw: FakeUploader(PostResult(True, "up")))
    assert isinstance(main._make_uploader("redditregrets"), FakeUploader)
    # profile dir exists -> the persistent-profile uploader wins
    (tmp_path / "profiles" / "redditregrets").mkdir(parents=True)
    up = main._make_uploader("redditregrets")
    assert type(up).__name__ == "ProfileUploader"
    assert up.account == "redditregrets"


def test_park_part2_moves_queued_video_to_outbox(tmp_path, monkeypatch):
    # part 1 failed: the sequel must not stay scheduled behind a missing opener
    redirect_paths(tmp_path, monkeypatch, with_video=False)
    queue_part2(tmp_path, monkeypatch)
    main._park_part2("s1")
    assert (tmp_path / "outbox" / "s1_p2.mp4").read_bytes() == b"part2"
    assert (tmp_path / "outbox" / "s1_p2.txt").read_text(
        encoding="utf-8").startswith("A tale")
    assert pending.next_entry(config.QUEUE_DIR, "redditregrets") is None
    main._park_part2("s1")   # nothing queued now: a no-op, not a crash


def test_post_mode_logs_when_no_story(tmp_path, monkeypatch):
    # a --post run that finds nothing still records the attempt, so posts.jsonl
    # tells a dry subreddit day apart from a scheduler that never fired
    redirect_paths(tmp_path, monkeypatch, with_video=False)
    # empty backgrounds dir -> plan_background falls back to the temp vid.mp4
    monkeypatch.setattr(config, "BACKGROUNDS_DIR", str(tmp_path / "bg"))
    monkeypatch.setattr(config, "INPUT_VID_PATH", str(tmp_path / "vid.mp4"))
    (tmp_path / "vid.mp4").write_bytes(b"clip")
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(main, "build_source",
                        lambda *a, **kw: SimpleNamespace(fetch=lambda: None))
    monkeypatch.setattr(
        sys, "argv",
        ["main.py", "--post", "--account", "redditregrets", "--dry-run"])
    assert main.main() == 0
    posts = read_posts(config.POST_LOG_PATH)
    assert len(posts) == 1
    assert posts[0]["story_id"] is None
    assert posts[0]["ok"] is None
    assert posts[0]["detail"] == "no story"
    assert posts[0]["account"] == "redditregrets"
