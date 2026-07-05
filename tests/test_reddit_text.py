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
