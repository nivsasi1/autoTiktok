import pytest

import tts
from subtitles import WordBoundary


def fake_synthesize(boundaries):
    async def fake(text, audio_path, voice):
        with open(audio_path, "wb") as f:
            f.write(b"mp3bytes")
        return boundaries
    return fake


def test_no_boundaries_leaves_no_file_behind(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "_synthesize", fake_synthesize([]))
    out = tmp_path / "output.mp3"
    with pytest.raises(RuntimeError, match="no word boundaries"):
        tts.synthesize("hello", str(out), "en-US-AriaNeural")
    # a failed run must not leave output.mp3 (or any temp sibling) behind
    assert list(tmp_path.iterdir()) == []


def test_success_writes_audio_and_returns_boundaries(tmp_path, monkeypatch):
    words = [WordBoundary("hello", 0.0, 0.5)]
    monkeypatch.setattr(tts, "_synthesize", fake_synthesize(words))
    out = tmp_path / "output.mp3"
    assert tts.synthesize("hello", str(out), "en-US-AriaNeural") == words
    assert out.read_bytes() == b"mp3bytes"
    assert [p.name for p in tmp_path.iterdir()] == ["output.mp3"]
