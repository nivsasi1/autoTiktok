import json
import os

import pending


def meta(story_id="s1", account="nosleeptonight", part=2):
    return {"story_id": story_id, "part": part, "account": account,
            "niche": "horror", "title": "T", "url": "u", "caption": "cap"}


def test_enqueue_moves_video_and_writes_sidecar(tmp_path):
    src = tmp_path / "out_part2.mp4"
    src.write_bytes(b"video")
    q = str(tmp_path / "queue")
    dst = pending.enqueue(q, str(src), meta())
    assert not src.exists()
    assert os.path.basename(dst) == "s1_p2.mp4"
    assert open(dst, "rb").read() == b"video"
    assert json.load(open(os.path.join(q, "s1_p2.json"),
                          encoding="utf-8"))["caption"] == "cap"


def test_next_entry_roundtrip_and_account_filter(tmp_path):
    q = str(tmp_path / "queue")
    src = tmp_path / "v.mp4"
    src.write_bytes(b"x")
    pending.enqueue(q, str(src), meta(account="nosleeptonight"))
    assert pending.next_entry(q, "redditregrets") is None
    video, m = pending.next_entry(q, "nosleeptonight")
    assert m["story_id"] == "s1" and video.endswith("s1_p2.mp4")


def test_next_entry_missing_dir_and_corrupt_sidecar(tmp_path):
    assert pending.next_entry(str(tmp_path / "nope"), "a") is None
    q = tmp_path / "queue"
    q.mkdir()
    (q / "bad.json").write_text("{not json", encoding="utf-8")
    assert pending.next_entry(str(q), "a") is None


def test_next_entry_skips_sidecar_without_video(tmp_path):
    q = tmp_path / "queue"
    q.mkdir()
    (q / "gone_p2.json").write_text(json.dumps(meta()), encoding="utf-8")
    assert pending.next_entry(str(q), "nosleeptonight") is None


def test_pop_takes_specific_entry(tmp_path):
    q = str(tmp_path / "queue")
    src = tmp_path / "v.mp4"
    src.write_bytes(b"x")
    pending.enqueue(q, str(src), meta(story_id="s9"))
    assert pending.pop(q, "other") is None
    video, m = pending.pop(q, "s9")
    assert video.endswith("s9_p2.mp4") and m["caption"] == "cap"
    assert not (tmp_path / "queue" / "s9_p2.json").exists()
    # sidecar gone -> the scheduler can no longer pick this entry up
    assert pending.next_entry(q, "nosleeptonight") is None


def test_remove_drops_video_and_sidecar(tmp_path):
    q = str(tmp_path / "queue")
    src = tmp_path / "v.mp4"
    src.write_bytes(b"x")
    dst = pending.enqueue(q, str(src), meta())
    pending.remove(dst)
    assert os.listdir(q) == []
    pending.remove(dst)   # idempotent: already-gone files are fine
