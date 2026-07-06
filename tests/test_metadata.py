import random
from types import SimpleNamespace

import config
from metadata import build_caption


def story(title):
    return SimpleNamespace(title=title)


def test_short_title_kept_and_tagged():
    cap = build_caption(story("Am I wrong?"), "drama", rng=random.Random(1))
    assert cap.startswith("Am I wrong? ")
    for tag in config.HASHTAGS["drama"]["fixed"]:
        assert tag in cap


def test_long_title_trimmed_at_word_boundary():
    long_title = "word " * 40   # 200 chars
    cap = build_caption(story(long_title.strip()), "drama",
                        rng=random.Random(1))
    head = cap.split(" #")[0]
    assert head.endswith("…")
    assert len(head) <= config.CAPTION_TITLE_CHARS + 1   # +1 for the ellipsis
    assert not head.rstrip("…").endswith("wor")          # no mid-word cut


def test_exactly_two_pool_tags_added():
    cap = build_caption(story("T"), "horror", rng=random.Random(7))
    tags = [w for w in cap.split() if w.startswith("#")]
    fixed = config.HASHTAGS["horror"]["fixed"]
    assert tags[:3] == fixed
    extra = tags[3:]
    assert len(extra) == 2
    assert all(t in config.HASHTAGS["horror"]["pool"] for t in extra)


def test_seeded_rng_is_deterministic():
    a = build_caption(story("T"), "drama", rng=random.Random(42))
    b = build_caption(story("T"), "drama", rng=random.Random(42))
    assert a == b


def test_part_label_lands_after_title_before_tags():
    cap = build_caption(story("A tale"), "horror", rng=random.Random(1), part=2)
    assert cap.startswith("A tale (Part 2/2) #")


def test_no_space_title_hard_cuts_at_limit():
    # a single very long token (e.g. a URL-ish title) has no word boundary;
    # a hard cut + ellipsis is the accepted fallback
    cap = build_caption(story("x" * 150), "drama", rng=random.Random(1))
    head = cap.split(" #")[0]
    assert head == "x" * config.CAPTION_TITLE_CHARS + "…"
