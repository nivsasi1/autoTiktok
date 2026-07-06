from types import SimpleNamespace

from sources.reddit_text import build_script, qualifies


def entry(**kw):
    base = dict(id="p1", kind="t3", author="/u/someone",
                title="A normal story", html="<p>story</p>")
    base.update(kw)
    return SimpleNamespace(**base)


def test_qualifies_accepts_normal_post():
    assert qualifies(entry(), used_ids=set())


def test_rejects_used_automod_nsfw_and_non_posts():
    assert not qualifies(entry(), used_ids={"p1"})
    assert not qualifies(entry(author="/u/AutoModerator"), used_ids=set())
    assert not qualifies(entry(title="[NSFW] wild story"), used_ids=set())
    assert not qualifies(entry(kind="t1"), used_ids=set())


def test_build_script_joins_title_body_outro():
    s = build_script("My title", "The story body.", "Comment below.")
    assert s == "My title. The story body. Comment below."


def test_build_script_keeps_title_end_punctuation():
    s = build_script("Am I wrong?", "Body.", "Outro.")
    assert s == "Am I wrong? Body. Outro."


def test_rejects_nsfw_tag_anywhere_in_title():
    assert not qualifies(entry(title="My wild story [NSFW]"), used_ids=set())


def test_fetch_returns_story_and_respects_min_chars(monkeypatch):
    import config
    from sources import reddit_text

    long_html = "<p>" + ("word " * 200) + "</p>"   # well over MIN_CHARS
    entries = [
        SimpleNamespace(id="short1", kind="t3", author="/u/a",
                        title="Too short", html="<p>tiny</p>", link="L1"),
        SimpleNamespace(id="good1", kind="t3", author="/u/b",
                        title="A story", html=long_html,
                        link="https://reddit/x"),
    ]
    seen = {}

    def fake_fetch(url):
        seen["url"] = url
        return entries

    monkeypatch.setattr(reddit_text, "fetch_entries", fake_fetch)
    preset = config.NICHES["drama"]
    story = reddit_text.RedditTextSource("drama", preset, set()).fetch()
    assert "hot.rss" in seen["url"] and "+".join(preset.subreddits) in seen["url"]
    assert story.id == "good1"                  # short one was rejected
    assert story.url == "https://reddit/x"
    assert story.niche == "drama"
    assert story.text.startswith("A story.")    # bare title got its period
    assert story.text.endswith(preset.outro)
