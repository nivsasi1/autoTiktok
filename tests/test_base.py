import json

import pytest

from sources.base import clean_text, load_used_ids, record_used_id


def test_clean_strips_markdown_links_and_urls():
    raw = "See [my post](https://x.com/a) and https://y.com/b now"
    assert clean_text(raw, 500) == "See my post and now"


def test_clean_strips_markdown_noise_and_entities():
    raw = "**bold** _it_ &amp; stuff &#x200B; here"
    assert clean_text(raw, 500) == "bold it and stuff here"


def test_clean_collapses_whitespace():
    assert clean_text("a\n\nb\t c", 500) == "a b c"


def test_truncates_at_sentence_boundary():
    raw = "First sentence. Second sentence. Third one that overflows badly."
    out = clean_text(raw, 35)
    assert out == "First sentence. Second sentence."


def test_truncates_at_space_when_no_sentence_end():
    out = clean_text("word " * 30, 32)
    assert len(out) <= 32
    assert not out.endswith(" ")


def test_state_roundtrip(tmp_path):
    p = str(tmp_path / "state.json")
    assert load_used_ids(p) == set()          # missing file -> empty
    record_used_id(p, "abc")
    record_used_id(p, "def")
    assert load_used_ids(p) == {"abc", "def"}
    data = json.loads(open(p, encoding="utf-8").read())
    assert sorted(data) == ["abc", "def"]     # stored as a JSON list


def test_state_survives_corrupt_file(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("not json", encoding="utf-8")
    assert load_used_ids(str(p)) == set()


def test_clean_url_in_parens_leaves_no_orphan_bracket():
    assert clean_text("Check this out(https://x.com/a).", 500) == "Check this out."


def test_clean_url_keeps_sentence_period():
    assert clean_text("Visit https://x.com/a.", 500) == "Visit."


def test_clean_url_with_trailing_comma():
    assert clean_text("Great link: https://x.com/a, right?", 500) == "Great link: right?"


def test_clean_nested_markdown_link():
    assert clean_text("See [my [nested] post](https://x.com/a) now", 500) == "See my nested post now"


def test_clean_unescapes_apostrophe_entity():
    assert clean_text("It&#39;s fine", 500) == "It's fine"


def test_truncate_without_spaces_keeps_full_cut():
    out = clean_text("word" * 20, 10)
    assert out == "wordwordwo"


class FakeResp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_get_json_returns_parsed_payload(monkeypatch):
    from sources import base
    monkeypatch.setattr(base.requests, "get",
                        lambda url, headers, timeout: FakeResp(200, {"ok": 1}))
    assert base.get_json("https://x") == {"ok": 1}


def test_get_json_sends_user_agent(monkeypatch):
    from sources import base
    seen = {}

    def fake_get(url, headers, timeout):
        seen.update(headers)
        return FakeResp(200, [])

    monkeypatch.setattr(base.requests, "get", fake_get)
    base.get_json("https://x")
    assert seen["User-Agent"]


def test_get_json_raises_clear_error_on_403(monkeypatch):
    from sources import base
    monkeypatch.setattr(base.requests, "get",
                        lambda url, headers, timeout: FakeResp(403))
    with pytest.raises(RuntimeError, match="REDDIT_USER_AGENT"):
        base.get_json("https://x")


def test_get_json_retries_429_then_succeeds(monkeypatch):
    from sources import base
    calls = []

    def fake_get(url, headers, timeout):
        calls.append(1)
        return FakeResp(429) if len(calls) == 1 else FakeResp(200, {"ok": 2})

    monkeypatch.setattr(base.requests, "get", fake_get)
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    assert base.get_json("https://x") == {"ok": 2}
    assert len(calls) == 2


def test_to_obj_gives_attribute_access():
    from sources.base import to_obj
    o = to_obj({"id": "x1", "over_18": False, "selftext": "hi"})
    assert o.id == "x1" and o.over_18 is False and o.selftext == "hi"
