from post_log import append_post, read_posts


def test_roundtrip_accumulates(tmp_path):
    p = str(tmp_path / "posts.jsonl")
    append_post(p, {"story_id": "a", "ok": True})
    append_post(p, {"story_id": "b", "ok": False, "title": "עברית ok"})
    posts = read_posts(p)
    assert [r["story_id"] for r in posts] == ["a", "b"]
    assert posts[1]["title"] == "עברית ok"   # utf-8, not escaped


def test_missing_file_reads_empty(tmp_path):
    assert read_posts(str(tmp_path / "nope.jsonl")) == []


def test_corrupt_line_skipped(tmp_path):
    p = tmp_path / "posts.jsonl"
    p.write_text('{"story_id": "a"}\nnot json\n{"story_id": "b"}\n',
                 encoding="utf-8")
    assert [r["story_id"] for r in read_posts(str(p))] == ["a", "b"]
