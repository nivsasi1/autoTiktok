from types import SimpleNamespace

import config
import pipeline
from subtitles import WordBoundary


def story():
    return SimpleNamespace(id="s1", title="T", text="hello world", url="u",
                           niche="horror")


def boundaries(narration, step=2.0):
    out, t = [], 0.0
    while t < narration - 1.0:
        out.append(WordBoundary("word.", t, t + step * 0.9))
        t += step
    return out


INTRO_LEN = 2.0


def wire(monkeypatch, narration, card="card.png"):
    """Stub the slow/external edges; keep split/subtitles logic real."""
    calls = {"cut": [], "render": [], "srt": [], "concat": []}

    def fake_synthesize(text, path, voice):
        if text.startswith("Part 2 of"):
            return [WordBoundary("Part", 0.0, 0.4),
                    WordBoundary("2.", 0.5, 1.0)]
        return boundaries(narration)

    def fake_duration(path):
        return INTRO_LEN if "intro" in path else narration

    def fake_card(*a, **kw):
        if card is None:
            raise OSError("no fonts")
        return card

    monkeypatch.setattr(pipeline.tts, "synthesize", fake_synthesize)
    monkeypatch.setattr(pipeline.video, "get_duration", fake_duration)
    monkeypatch.setattr(pipeline.video, "cut_audio",
                        lambda *a: calls["cut"].append(a))
    monkeypatch.setattr(pipeline.video, "concat_audio",
                        lambda *a: calls["concat"].append(a))
    monkeypatch.setattr(pipeline.hookcard, "make_card", fake_card)
    monkeypatch.setattr(pipeline.subtitles, "write_ass",
                        lambda *a, **kw: calls["srt"].append((a, kw)))
    monkeypatch.setattr(
        pipeline, "_render",
        lambda niche, audio, srt, out, card=None, log=None:
        calls["render"].append((out, card)))
    return calls


def test_short_story_renders_one_video_with_card(monkeypatch):
    calls = wire(monkeypatch, narration=60.0)
    result = pipeline.render_story(story(), config.NICHES["horror"], "horror",
                                   log=lambda m: None)
    assert result.videos == [(config.OUTPUT_VID_PATH, None)]
    assert not result.split
    assert calls["cut"] == []                       # no audio slicing
    assert calls["render"] == [(config.OUTPUT_VID_PATH, "card.png")]
    assert calls["srt"][0][1].get("hook") is None   # card replaces text hook


def test_card_failure_falls_back_to_text_hook(monkeypatch):
    calls = wire(monkeypatch, narration=60.0, card=None)
    pipeline.render_story(story(), config.NICHES["horror"], "horror",
                          log=lambda m: None)
    assert calls["render"] == [(config.OUTPUT_VID_PATH, None)]
    assert calls["srt"][0][1].get("hook") == "T"


def test_long_story_renders_two_parts_with_spoken_intro(monkeypatch):
    calls = wire(monkeypatch, narration=160.0)
    result = pipeline.render_story(story(), config.NICHES["horror"], "horror",
                                   log=lambda m: None)
    assert result.split
    assert [p for _, p in result.videos] == [1, 2]
    # card on part 1 only
    assert calls["render"][0] == (config.OUTPUT_VID_PATH, "card.png")
    assert calls["render"][1] == (config.OUTPUT_PART2_PATH, None)
    # part 1 slice + part 2 tail slice cut, then intro glued on
    assert len(calls["cut"]) == 2
    assert len(calls["concat"]) == 1
    # part 2 captions open with the spoken intro, shifted to its audio
    part2_bounds = calls["srt"][1][0][0]
    assert part2_bounds[0].word == "Part"
    assert part2_bounds[2].start >= INTRO_LEN       # story words after intro
    for (_args, kw) in calls["srt"]:
        assert kw.get("extra_cues")                 # PART labels everywhere
    assert calls["srt"][0][1].get("hook") is None   # card covers part 1
    assert calls["srt"][1][1].get("hook") is None
