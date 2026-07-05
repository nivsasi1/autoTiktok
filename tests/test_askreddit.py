from types import SimpleNamespace

from sources.askreddit import build_script, usable_comment


def centry(**kw):
    base = dict(id="c1", kind="t1", author="/u/replier",
                html="<p>A solid answer here.</p>")
    base.update(kw)
    return SimpleNamespace(**base)


def test_usable_comment_filters():
    assert usable_comment(centry())
    assert not usable_comment(centry(kind="t3"))
    assert not usable_comment(centry(author="/u/AutoModerator"))
    assert not usable_comment(centry(author=""))
    assert not usable_comment(centry(html="   "))


def test_build_script_numbers_answers():
    s = build_script("Weirdest thing seen at night?",
                     ["A fox in a hat.", "Nothing, ever."], "Comment below.")
    assert s == ("Weirdest thing seen at night? Number 1. A fox in a hat. "
                 "Number 2. Nothing, ever. Comment below.")


def test_build_script_adds_question_mark_to_bare_title():
    s = build_script("Weirdest thing seen at night", ["An owl."], "Bye.")
    assert s.startswith("Weirdest thing seen at night? Number 1.")


def test_build_script_stops_before_max_chars():
    answers = [f"Answer number {i} padded out to be long." for i in range(50)]
    s = build_script("Q?", answers, "Out.", max_chars=300)
    assert len(s) <= 300
    assert s.endswith("Out.")
    assert "Number 1." in s and "Number 50." not in s
