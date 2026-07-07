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


def wb(word, i):
    return WordBoundary(word, float(i), i + 0.5)


def test_restore_punctuation_reattaches_sentence_ends():
    # edge-tts strips punctuation from boundary words; the source text has it
    text = "I laughed. He cried! Did you see that?"
    bounds = [wb(w, i) for i, w in
              enumerate("I laughed He cried Did you see that".split())]
    out = tts._restore_punctuation(bounds, text)
    assert [b.word for b in out] == text.split()
    assert out[1].start == bounds[1].start        # timings untouched


def test_restore_punctuation_handles_repeats_and_case():
    text = "The dog saw the Dog."
    bounds = [wb(w, i) for i, w in enumerate("The dog saw the Dog".split())]
    out = tts._restore_punctuation(bounds, text)
    assert out[-1].word == "Dog."
    assert out[1].word == "dog" and out[3].word == "the"


def test_restore_punctuation_keeps_unmatched_words():
    # engine sometimes rewrites tokens (numbers, dates) — those pass through
    text = "It was 3 AM. Quiet."
    bounds = [wb("It", 0), wb("was", 1), wb("three", 2), wb("AM", 3),
              wb("Quiet", 4)]
    out = tts._restore_punctuation(bounds, text)
    assert out[2].word == "three"                 # no match -> unchanged
    assert out[3].word == "AM."                   # resyncs after the miss
    assert out[4].word == "Quiet."
