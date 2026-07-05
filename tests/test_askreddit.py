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


def test_fetch_walks_posts_and_assembles_story(monkeypatch):
    import config
    from sources import askreddit

    def post(pid, author="/u/asker"):
        return SimpleNamespace(id=pid, kind="t3", author=author,
                               title=f"Question {pid}",
                               link=f"https://reddit/{pid}/", html="")

    good_answer = "<p>" + "a decent answer to the question here. " * 2 + "</p>"
    calls = []

    def fake_fetch(url):
        calls.append(url)
        if "hot.rss" in url:
            return [post("used1"), post("auto1", author="/u/AutoModerator"),
                    post("thin1"), post("good1")]
        if "/thin1/" in url:                    # 1 usable answer -> fall through
            return [centry(id="c0", html=good_answer)]
        if "/good1/" in url:                    # post itself first, then answers
            return [SimpleNamespace(id="good1", kind="t3", author="/u/asker",
                                    title="", link="", html="post body")] + [
                centry(id=f"c{i}", html=good_answer) for i in range(5)]
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(askreddit, "fetch_entries", fake_fetch)
    preset = config.NICHES["askreddit"]
    story = askreddit.AskRedditSource(preset, used_ids={"used1"}).fetch()

    assert story.id == "good1" and story.niche == "askreddit"
    assert story.url == "https://reddit/good1/"
    assert story.text.startswith("Question good1?")   # bare title got "?"
    assert "Number 1." in story.text and "Number 3." in story.text
    assert story.text.endswith(preset.outro)
    # listing once; comments fetched ONLY for thin1 (rejected) and good1
    assert calls[0].endswith("hot.rss?limit=25")
    assert calls[1:] == ["https://reddit/thin1/.rss?limit=25",
                         "https://reddit/good1/.rss?limit=25"]
