import json
import re
import sys
from types import SimpleNamespace

import config
import main
import outbox
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
    # and never send real failure emails from tests
    monkeypatch.setattr(config, "NOTIFY_EMAIL_TO", "")
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


def test_uploader_prefers_verified_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILES_DIR", str(tmp_path / "profiles"))
    cookies = tmp_path / "c.txt"
    cookies.write_text("k=v", encoding="utf-8")
    monkeypatch.setattr(config.ACCOUNTS["redditregrets"], "cookies_file",
                        str(cookies))
    monkeypatch.setattr(main, "CookieUploader",
                        lambda *a, **kw: FakeUploader(PostResult(True, "up")))
    # a profile dir that ISN'T logged in must not win over working cookies
    (tmp_path / "profiles" / "redditregrets").mkdir(parents=True)
    monkeypatch.setattr(main, "profile_logged_in", lambda p: False)
    assert isinstance(main._make_uploader("redditregrets"), FakeUploader)
    # verified login -> the persistent-profile uploader wins
    monkeypatch.setattr(main, "profile_logged_in", lambda p: True)
    up = main._make_uploader("redditregrets")
    assert type(up).__name__ == "ProfileUploader"
    assert up.account == "redditregrets"
    # nothing at all -> profile uploader, whose error names the --login fix
    monkeypatch.setattr(main, "profile_logged_in", lambda p: False)
    monkeypatch.setattr(config.ACCOUNTS["redditregrets"], "cookies_file",
                        str(tmp_path / "missing.txt"))
    assert type(main._make_uploader("redditregrets")).__name__ \
        == "ProfileUploader"


def test_upload_failure_sends_notification(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch)
    sent = []
    monkeypatch.setattr(main.notify, "send_failure",
                        lambda subject, body: sent.append((subject, body)))
    monkeypatch.setattr(main, "CookieUploader",
                        lambda *a, **kw: FakeUploader(PostResult(False, "boom")))
    assert main._publish(story(), "redditregrets", dry_run=False) == 1
    (subject, body), = sent
    assert "redditregrets" in subject
    assert "boom" in body and "A tale" in body


def test_successful_upload_sends_no_notification(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(
        main.notify, "send_failure",
        lambda *a: (_ for _ in ()).throw(AssertionError("emailed")))
    monkeypatch.setattr(main, "CookieUploader",
                        lambda *a, **kw: FakeUploader(PostResult(True, "up")))
    assert main._publish(story(), "redditregrets", dry_run=False) == 0


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


def park_failed_p1(tmp_path, account="redditregrets", attempts=0):
    src = tmp_path / "failed.mp4"
    src.write_bytes(b"parked")
    return outbox.park(config.OUTBOX_DIR,
                       str(src), {"story_id": "s7", "part": 1,
                                  "account": account, "niche": "drama",
                                  "title": "Parked tale", "url": "u",
                                  "caption": "cap", "attempts": attempts})


def post_argv(monkeypatch, *extra):
    monkeypatch.setattr(config, "POST_JITTER_MAX_S", 0)
    monkeypatch.setattr(
        sys, "argv", ["main.py", "--post", "--account", "redditregrets",
                      *extra])


def test_outbox_retry_runs_before_fetching_new_story(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch, with_video=False)
    parked = park_failed_p1(tmp_path)
    cookies = tmp_path / "c.txt"
    cookies.write_text("k=v", encoding="utf-8")
    monkeypatch.setattr(config.ACCOUNTS["redditregrets"], "cookies_file",
                        str(cookies))
    monkeypatch.setattr(main, "CookieUploader",
                        lambda *a, **kw: FakeUploader(PostResult(True, "up")))
    monkeypatch.setattr(
        main, "build_source",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("fetched")))
    post_argv(monkeypatch)
    assert main.main() == 0
    rec = read_posts(config.POST_LOG_PATH)[0]
    assert rec["ok"] is True and rec["story_id"] == "s7"
    assert not (tmp_path / "outbox" / "s7_p1.mp4").exists()   # cleared
    assert parked not in [v for v, _ in outbox.entries(config.OUTBOX_DIR)]


def test_outbox_retry_failure_bumps_attempts_and_keeps_video(tmp_path,
                                                             monkeypatch):
    redirect_paths(tmp_path, monkeypatch, with_video=False)
    park_failed_p1(tmp_path, attempts=1)
    cookies = tmp_path / "c.txt"
    cookies.write_text("k=v", encoding="utf-8")
    monkeypatch.setattr(config.ACCOUNTS["redditregrets"], "cookies_file",
                        str(cookies))
    monkeypatch.setattr(main, "CookieUploader",
                        lambda *a, **kw: FakeUploader(PostResult(False, "boom")))
    monkeypatch.setattr(
        main, "build_source",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("fetched")))
    post_argv(monkeypatch)
    assert main.main() == 1
    sidecar = tmp_path / "outbox" / "s7_p1.json"
    assert json.load(open(sidecar, encoding="utf-8"))["attempts"] == 2
    assert (tmp_path / "outbox" / "s7_p1.mp4").exists()


def test_outbox_dry_run_reports_but_changes_nothing(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch, with_video=False)
    park_failed_p1(tmp_path)
    monkeypatch.setattr(
        main, "CookieUploader",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("constructed")))
    monkeypatch.setattr(
        main, "build_source",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("fetched")))
    post_argv(monkeypatch, "--dry-run")
    assert main.main() == 0
    sidecar = tmp_path / "outbox" / "s7_p1.json"
    assert json.load(open(sidecar, encoding="utf-8"))["attempts"] == 0


def test_status_smoke(tmp_path, monkeypatch, capsys):
    redirect_paths(tmp_path, monkeypatch, with_video=False)
    park_failed_p1(tmp_path, attempts=3)
    queue_part2(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["main.py", "--status"])
    assert main.main() == 0
    out = capsys.readouterr().out
    assert "redditregrets" in out and "nosleeptonight" in out
    assert "part 2 for redditregrets" in out
    assert "retries exhausted" in out
    assert "NO LOGIN" in out or "cookies file" in out or "profile" in out


def live_post_setup(tmp_path, monkeypatch):
    """A queued part 2 + working cookies: shortest path to a real --post run."""
    redirect_paths(tmp_path, monkeypatch, with_video=False)
    queue_part2(tmp_path, monkeypatch)
    cookies = tmp_path / "c.txt"
    cookies.write_text("k=v", encoding="utf-8")
    monkeypatch.setattr(config.ACCOUNTS["redditregrets"], "cookies_file",
                        str(cookies))
    monkeypatch.setattr(main, "CookieUploader",
                        lambda *a, **kw: FakeUploader(PostResult(True, "up")))


def test_post_announces_jitter_before_sleeping(tmp_path, monkeypatch, capsys):
    # a silent 0-15 min sleep looks like a hang from the terminal
    live_post_setup(tmp_path, monkeypatch)
    slept = []
    monkeypatch.setattr(main.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(main.random, "uniform", lambda a, b: 90.0)
    monkeypatch.setattr(
        sys, "argv", ["main.py", "--post", "--account", "redditregrets"])
    assert main.main() == 0
    assert slept == [90.0]
    out = capsys.readouterr().out
    assert "1.5 min" in out and "--now" in out


def test_now_flag_skips_jitter(tmp_path, monkeypatch):
    live_post_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        main.time, "sleep",
        lambda s: (_ for _ in ()).throw(AssertionError("slept")))
    monkeypatch.setattr(
        sys, "argv",
        ["main.py", "--post", "--account", "redditregrets", "--now"])
    assert main.main() == 0


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


def test_account_lock_blocks_concurrent_live_posts(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch, with_video=False)
    lock = main._acquire_account_lock("redditregrets")
    assert lock and lock.endswith("redditregrets.lock")
    assert main._acquire_account_lock("redditregrets") is None   # held
    assert main._acquire_account_lock("nosleeptonight")          # other ok
    main._release_account_lock(lock)
    assert main._acquire_account_lock("redditregrets")           # free again


def test_stale_account_lock_is_reclaimed(tmp_path, monkeypatch):
    import os
    import time as _time
    redirect_paths(tmp_path, monkeypatch, with_video=False)
    lock = main._acquire_account_lock("redditregrets")
    old = _time.time() - 3 * 3600
    os.utime(lock, (old, old))                      # owner died 3h ago
    assert main._acquire_account_lock("redditregrets") == lock


def test_concurrent_live_post_skips_slot_and_logs(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch, with_video=False)
    main._acquire_account_lock("redditregrets")     # someone else is posting
    monkeypatch.setattr(
        main, "_run", lambda a: (_ for _ in ()).throw(AssertionError("ran")))
    post_argv(monkeypatch)
    assert main.main() == 0
    rec = read_posts(config.POST_LOG_PATH)[0]
    assert rec["detail"] == "skipped: concurrent run"


def test_lock_released_after_run(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch, with_video=False)
    monkeypatch.setattr(main, "_run", lambda a: 0)
    post_argv(monkeypatch)
    assert main.main() == 0
    assert main._acquire_account_lock("redditregrets")  # lock was released
