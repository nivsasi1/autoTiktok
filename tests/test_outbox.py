import json
import os
import time

import outbox


def meta(story_id="s1", account="redditregrets", part=None, attempts=0):
    m = {"story_id": story_id, "account": account, "niche": "drama",
         "title": "T", "url": "u", "caption": "cap", "attempts": attempts}
    if part:
        m["part"] = part
    return m


def park_one(tmp_path, name="v.mp4", **kw):
    src = tmp_path / name
    src.write_bytes(b"x")
    return outbox.park(str(tmp_path / "outbox"), str(src), meta(**kw))


def test_park_writes_video_sidecar_and_caption(tmp_path):
    parked = park_one(tmp_path, story_id="s1", part=2)
    assert os.path.basename(parked) == "s1_p2.mp4"
    stem = os.path.splitext(parked)[0]
    assert json.load(open(stem + ".json", encoding="utf-8"))["attempts"] == 0
    assert open(stem + ".txt", encoding="utf-8").read() == "cap"


def test_next_retry_filters_account_and_attempt_cap(tmp_path):
    park_one(tmp_path, "a.mp4", story_id="a", account="other")
    park_one(tmp_path, "b.mp4", story_id="b", attempts=3)
    park_one(tmp_path, "c.mp4", story_id="c")
    got = outbox.next_retry(str(tmp_path / "outbox"), "redditregrets", 3)
    assert got and got[1]["story_id"] == "c"


def test_bump_attempts_does_not_reorder_retries(tmp_path):
    d = str(tmp_path / "outbox")
    first = park_one(tmp_path, "a.mp4", story_id="older")
    time.sleep(0.02)
    park_one(tmp_path, "b.mp4", story_id="newer")
    video, m = outbox.next_retry(d, "redditregrets", 3)
    assert m["story_id"] == "older"
    outbox.bump_attempts(d, video, m)   # rewrites the sidecar
    video2, m2 = outbox.next_retry(d, "redditregrets", 3)
    assert m2["story_id"] == "older"    # video mtime keeps it first
    assert m2["attempts"] == 1
    outbox.bump_attempts(d, video2, m2)
    outbox.bump_attempts(d, video2, {**m2, "attempts": 2})
    _, m3 = outbox.next_retry(d, "redditregrets", 3)
    assert m3["story_id"] == "newer"    # older exhausted its 3 attempts
    assert os.path.exists(first)        # but stays parked for manual posting


def test_part2_waits_for_its_part1(tmp_path):
    d = str(tmp_path / "outbox")
    park_one(tmp_path, "p1.mp4", story_id="s1", part=1)
    time.sleep(0.02)
    park_one(tmp_path, "p2.mp4", story_id="s1", part=2)
    _, m = outbox.next_retry(d, "redditregrets", 3)
    assert m.get("part") == 1
    # part 1 posted (cleared) -> part 2 becomes eligible
    outbox.clear(os.path.join(d, "s1_p1.mp4"))
    _, m = outbox.next_retry(d, "redditregrets", 3)
    assert m.get("part") == 2


def test_legacy_files_without_sidecar_are_ignored(tmp_path):
    d = tmp_path / "outbox"
    d.mkdir()
    (d / "old.mp4").write_bytes(b"x")
    (d / "old.txt").write_text("cap", encoding="utf-8")
    assert outbox.entries(str(d)) == []
    assert outbox.next_retry(str(d), "redditregrets", 3) is None


def test_clear_removes_all_three_files(tmp_path):
    parked = park_one(tmp_path)
    outbox.clear(parked)
    assert os.listdir(tmp_path / "outbox") == []
    outbox.clear(parked)   # idempotent