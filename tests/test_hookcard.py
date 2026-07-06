import random

from PIL import Image

import hookcard


def test_card_renders_png_with_reddit_shape(tmp_path):
    out = str(tmp_path / "card.png")
    got = hookcard.make_card("AITA for laughing at dinner?", "redditregrets",
                             out, rng=random.Random(1))
    img = Image.open(got)
    assert img.width == hookcard.CARD_W
    assert img.mode == "RGBA"


def test_long_titles_wrap_and_grow_the_card(tmp_path):
    short = Image.open(hookcard.make_card(
        "Short title", "x", str(tmp_path / "a.png"), rng=random.Random(1)))
    long_ = Image.open(hookcard.make_card(
        "A very long dramatic title that should wrap onto several lines "
        "because it just keeps going and going", "x",
        str(tmp_path / "b.png"), rng=random.Random(1)))
    assert long_.height > short.height


def test_missing_avatar_uses_placeholder(tmp_path):
    got = hookcard.make_card("T", "x", str(tmp_path / "c.png"),
                             avatar_path=str(tmp_path / "nope.png"),
                             rng=random.Random(1))
    assert Image.open(got).height > 0
