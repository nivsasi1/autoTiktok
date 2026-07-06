from types import SimpleNamespace

import pytest

import config
import sources.reddit_url as reddit_url
from sources.freeform import FreeformSource
from sources.reddit_url import RedditUrlSource

PRESET = config.NICHES["horror"]
BODY = "<p>" + "Something moved in the dark. " * 20 + "</p>"


def entry(kind="t3", eid="abc123", html=BODY):
    return SimpleNamespace(kind=kind, id=eid, title="The Cellar",
                           html=html, author="/u/someone",
                           link="https://reddit.com/r/nosleep/comments/abc123/")


def url_source(url="https://www.reddit.com/r/nosleep/comments/abc123/the_cellar/"):
    return RedditUrlSource(url, PRESET, "horror")


def test_url_source_fetches_the_post_entry(monkeypatch):
    seen = {}

    def fake_fetch(url):
        seen["url"] = url
        return [entry(kind="t1", eid="comment1"), entry()]

    monkeypatch.setattr(reddit_url, "fetch_entries", fake_fetch)
    story = url_source().fetch()
    assert seen["url"].endswith("/the_cellar.rss?limit=1")
    assert story.id == "abc123"
    assert story.title == "The Cellar"
    assert story.text.endswith(PRESET.outro)


def test_url_source_strips_query_and_fragment(monkeypatch):
    seen = {}
    monkeypatch.setattr(reddit_url, "fetch_entries",
                        lambda url: seen.update(url=url) or [entry()])
    url_source("https://www.reddit.com/r/nosleep/comments/abc123/x/?share_id=1#top").fetch()
    assert "?share_id" not in seen["url"].replace(".rss?limit=1", "")
    assert "#" not in seen["url"]


@pytest.mark.parametrize("bad", ["", "not a url", "https://example.com/post",
                                 "https://www.reddit.com/r/nosleep/"])
def test_url_source_rejects_non_post_urls(bad):
    with pytest.raises(ValueError, match="reddit post URL"):
        url_source(bad).fetch()


def test_url_source_errors_when_post_missing_or_empty(monkeypatch):
    monkeypatch.setattr(reddit_url, "fetch_entries", lambda url: [])
    with pytest.raises(ValueError, match="still up"):
        url_source().fetch()
    monkeypatch.setattr(reddit_url, "fetch_entries",
                        lambda url: [entry(html="<p>link</p>")])
    with pytest.raises(ValueError, match="no story text"):
        url_source().fetch()


def test_freeform_builds_story_with_stable_hash_id():
    src = FreeformSource("My night", "Something moved in the dark. " * 5,
                         PRESET, "horror")
    a, b = src.fetch(), src.fetch()
    assert a.id == b.id and a.id.startswith("freeform-")
    assert a.text.startswith("My night.")
    assert a.text.endswith(PRESET.outro)


def test_freeform_rejects_missing_title_or_short_text():
    with pytest.raises(ValueError, match="title"):
        FreeformSource("", "long enough text " * 10, PRESET, "horror").fetch()
    with pytest.raises(ValueError, match="too short"):
        FreeformSource("T", "tiny", PRESET, "horror").fetch()
