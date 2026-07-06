import pytest

import config
import gui


def test_build_story_freeform_and_url_route(monkeypatch):
    story = gui._build_story("freeform", "horror", "",
                             "My night", "Something moved in the dark. " * 5)
    assert story.id.startswith("freeform-")
    with pytest.raises(ValueError, match="reddit post URL"):
        gui._build_story("reddit url", "horror", "nope", "", "")


def test_build_story_auto_raises_friendly_when_feed_dry(monkeypatch):
    class Dry:
        def fetch(self):
            return None

    monkeypatch.setattr(gui, "build_source", lambda *a: Dry())
    with pytest.raises(ValueError, match="no qualifying"):
        gui._build_story("auto", "drama", "", "", "")


def test_do_post_guards():
    assert gui.do_post(None, "c", "", "nosleeptonight", True) \
        == "render something first"
    assert gui.do_post({"niche": "drama"}, "c", "", None, True) \
        == "pick an account"
    msg = gui.do_post({"niche": "drama", "id": "x", "title": "t", "url": "",
                       "split": False}, "c", "", "nosleeptonight", True)
    assert "posts horror" in msg and "matching" in msg


def test_do_post_dry_run_split_never_queues(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "POST_LOG_PATH", str(tmp_path / "posts.jsonl"))
    monkeypatch.setattr(config, "QUEUE_DIR", str(tmp_path / "queue"))
    state = {"id": "s1", "title": "T", "url": "u", "niche": "horror",
             "split": True}
    msg = gui.do_post(state, "cap1", "cap2", "nosleeptonight", True)
    assert "would queue" in msg
    assert not (tmp_path / "queue").exists()


def test_voice_list_has_preset_default_first():
    assert gui.VOICES[0] == gui.PRESET_VOICE
    assert "en-US-GuyNeural" in gui.VOICES
