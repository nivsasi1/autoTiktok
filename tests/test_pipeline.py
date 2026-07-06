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


def wire(monkeypatch, narration):
    """Stub the slow/external edges; keep split/subtitles logic real."""
    calls = {"cut": [], "render": [], "srt": []}
    monkeypatch.setattr(pipeline.tts, "synthesize",
                        lambda text, path, voice: boundaries(narration))
    monkeypatch.setattr(pipeline.video, "get_duration", lambda p: narration)
    monkeypatch.setattr(pipeline.video, "cut_audio",
                        lambda *a: calls["cut"].append(a))
    monkeypatch.setattr(pipeline.subtitles, "write_srt",
                        lambda *a, **kw: calls["srt"].append((a, kw)))
    monkeypatch.setattr(
        pipeline, "_render",
        lambda niche, audio, srt, out, log=None: calls["render"].append(out))
    return calls


def test_short_story_renders_one_video(monkeypatch):
    calls = wire(monkeypatch, narration=60.0)
    result = pipeline.render_story(story(), config.NICHES["horror"], "horror",
                                   log=lambda m: None)
    assert result.videos == [(config.OUTPUT_VID_PATH, None)]
    assert not result.split
    assert calls["cut"] == []                       # no audio slicing
    assert calls["render"] == [config.OUTPUT_VID_PATH]


def test_long_story_renders_two_parts(monkeypatch):
    calls = wire(monkeypatch, narration=160.0)
    result = pipeline.render_story(story(), config.NICHES["horror"], "horror",
                                   log=lambda m: None)
    assert result.split
    assert [p for _, p in result.videos] == [1, 2]
    assert calls["render"] == [config.OUTPUT_VID_PATH,
                               config.OUTPUT_PART2_PATH]
    assert len(calls["cut"]) == 2                   # both slices cut
    # each part got label cues merged into its srt
    for (_args, kw) in calls["srt"]:
        assert kw.get("extra_cues")
