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


def test_record_used_id_survives_crash_mid_write(tmp_path, monkeypatch):
    from sources import base
    p = str(tmp_path / "state.json")
    record_used_id(p, "abc")

    def dying_dump(obj, f, **kw):   # crash after a partial write
        f.write('["partial')
        raise OSError("disk full")

    monkeypatch.setattr(base.json, "dump", dying_dump)
    with pytest.raises(OSError):
        record_used_id(p, "def")
    assert load_used_ids(p) == {"abc"}   # old state intact, not reset to empty
    # and the failed temp was cleaned up, not orphaned
    assert [f.name for f in tmp_path.iterdir()] == ["state.json"]


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


FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <author><name>/u/writer</name></author>
    <id>t3_abc12</id>
    <link href="https://www.reddit.com/r/stories/comments/abc12/tale/"/>
    <title>A tale</title>
    <content type="html">&lt;div class="md"&gt;&lt;p&gt;Hello story.&lt;/p&gt;&lt;/div&gt; submitted by &lt;a&gt;/u/writer&lt;/a&gt; [link] [comments]</content>
  </entry>
  <entry>
    <author><name>/u/replier</name></author>
    <id>t1_xyz99</id>
    <link href="https://www.reddit.com/r/stories/comments/abc12/tale/xyz99/"/>
    <title>replier on A tale</title>
    <content type="html">&lt;p&gt;Nice one.&lt;/p&gt;</content>
  </entry>
</feed>"""


class FakeResp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


def test_fetch_text_sends_user_agent(monkeypatch):
    from sources import base
    seen = {}

    def fake_get(url, headers, timeout):
        seen.update(headers)
        return FakeResp(200, "ok")

    monkeypatch.setattr(base.requests, "get", fake_get)
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    assert base.fetch_text("https://x") == "ok"
    assert seen["User-Agent"]


def test_fetch_text_raises_clear_error_on_403(monkeypatch):
    from sources import base
    monkeypatch.setattr(base.requests, "get",
                        lambda url, headers, timeout: FakeResp(403))
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="REDDIT_USER_AGENT"):
        base.fetch_text("https://x")


def test_fetch_text_retries_429_then_succeeds(monkeypatch):
    from sources import base
    calls = []

    def fake_get(url, headers, timeout):
        calls.append(1)
        return FakeResp(429) if len(calls) == 1 else FakeResp(200, "fine")

    monkeypatch.setattr(base.requests, "get", fake_get)
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    assert base.fetch_text("https://x") == "fine"
    assert len(calls) == 2


def test_fetch_text_retries_network_errors_then_raises(monkeypatch):
    from sources import base

    def boom(url, headers, timeout):
        raise base.requests.ConnectionError("no wifi")

    monkeypatch.setattr(base.requests, "get", boom)
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="network"):
        base.fetch_text("https://x")


def test_fetch_entries_parses_atom(monkeypatch):
    from sources import base
    monkeypatch.setattr(base, "fetch_text", lambda url: FEED)
    posts = base.fetch_entries("https://x")
    assert posts[0].kind == "t3" and posts[0].id == "abc12"
    assert posts[0].author == "/u/writer"
    assert posts[0].title == "A tale"
    assert posts[0].link.endswith("/tale/")
    assert "Hello story." in posts[0].html
    assert posts[1].kind == "t1" and posts[1].id == "xyz99"


def test_html_to_text_strips_tags_and_trailer():
    from sources.base import html_to_text
    frag = ('<div class="md"><p>Hello story.</p></div> submitted by '
            '<a href="u">/u/writer</a> <span>[link]</span> <span>[comments]</span>')
    assert " ".join(html_to_text(frag).split()) == "Hello story."


def test_html_to_text_keeps_prose_mentioning_submitted_by():
    from sources.base import html_to_text
    frag = "<p>I saw a post submitted by /u/foo yesterday. It got worse.</p>"
    out = " ".join(html_to_text(frag).split())
    assert out == "I saw a post submitted by /u/foo yesterday. It got worse."


def test_fetch_entries_raises_on_non_xml(monkeypatch):
    from sources import base
    monkeypatch.setattr(base, "fetch_text", lambda url: "<html>unclosed")
    with pytest.raises(RuntimeError, match="non-feed"):
        base.fetch_entries("https://x")


def test_fetch_entries_raises_on_html_page(monkeypatch):
    from sources import base
    monkeypatch.setattr(base, "fetch_text",
                        lambda url: "<html><body>blocked</body></html>")
    with pytest.raises(RuntimeError, match="non-feed"):
        base.fetch_entries("https://x")


def test_html_to_text_compound_prose_and_real_trailer():
    from sources.base import html_to_text
    frag = ("<p>I saw a post submitted by /u/foo earlier. The drama grew.</p> "
            "submitted by <a>/u/writer</a> <span>[link]</span> "
            "<span>[comments]</span>")
    out = " ".join(html_to_text(frag).split())
    assert out == "I saw a post submitted by /u/foo earlier. The drama grew."


def test_fetch_entries_drops_linkless_entries(monkeypatch):
    from sources import base
    feed = FEED.replace(
        '<link href="https://www.reddit.com/r/stories/comments/abc12/tale/"/>',
        "")
    monkeypatch.setattr(base, "fetch_text", lambda url: feed)
    # the link-less t3 entry is filtered at the source; consumers never see it
    assert [e.id for e in base.fetch_entries("https://x")] == ["xyz99"]
