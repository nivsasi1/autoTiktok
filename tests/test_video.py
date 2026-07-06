import random
import subprocess

import pytest

import video
from video import build_cmd, pick_background


def fake_probe(stdout):
    return lambda *a, **kw: subprocess.CompletedProcess(
        args=a, returncode=0, stdout=stdout, stderr="")


def test_pick_background_chooses_from_folder(tmp_path):
    for name in ("a.mp4", "b.mp4", "c.mp4"):
        (tmp_path / name).write_bytes(b"clip")
    chosen = pick_background(str(tmp_path), "vid.mp4", rng=random.Random(1))
    assert chosen.endswith(".mp4")
    assert chosen in [str(tmp_path / n) for n in ("a.mp4", "b.mp4", "c.mp4")]


def test_pick_background_finds_clips_in_subfolders(tmp_path):
    # users organize clips into niche subfolders; the glob must recurse
    (tmp_path / "horror").mkdir()
    (tmp_path / "scenic").mkdir()
    (tmp_path / "horror" / "cave.mp4").write_bytes(b"clip")
    (tmp_path / "scenic" / "beach.mp4").write_bytes(b"clip")
    chosen = pick_background(str(tmp_path), "vid.mp4", rng=random.Random(1))
    assert chosen in (str(tmp_path / "horror" / "cave.mp4"),
                      str(tmp_path / "scenic" / "beach.mp4"))


def test_pick_background_ignores_non_mp4(tmp_path):
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    (tmp_path / "only.mp4").write_bytes(b"clip")
    assert pick_background(str(tmp_path), "vid.mp4") == str(tmp_path / "only.mp4")


def test_pick_background_falls_back_when_folder_empty(tmp_path):
    fallback = tmp_path / "vid.mp4"
    fallback.write_bytes(b"clip")
    empty = tmp_path / "backgrounds"    # does not exist
    assert pick_background(str(empty), str(fallback)) == str(fallback)


def test_pick_background_raises_when_nothing(tmp_path):
    empty = tmp_path / "backgrounds"
    missing_fallback = tmp_path / "vid.mp4"
    with pytest.raises(RuntimeError, match="no background clip"):
        pick_background(str(empty), str(missing_fallback))


def test_get_duration_parses_ffprobe_output(monkeypatch):
    monkeypatch.setattr(video.subprocess, "run", fake_probe("12.34\n"))
    assert video.get_duration("clip.mp4") == 12.34


@pytest.mark.parametrize("stdout", ["", "N/A\n", "nan\n", "inf\n", "0\n"])
def test_get_duration_raises_runtime_error_on_unparsable_output(monkeypatch, stdout):
    monkeypatch.setattr(video.subprocess, "run", fake_probe(stdout))
    with pytest.raises(RuntimeError, match=r"ffprobe.*clip\.mp4"):
        video.get_duration("clip.mp4")


def test_export_error_includes_ffmpeg_stderr(monkeypatch):
    def fake_run(*a, **kw):
        return subprocess.CompletedProcess(
            args=a, returncode=1, stdout="", stderr="frame=1\nConversion failed!")

    monkeypatch.setattr(video.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="Conversion failed"):
        video.export("v.mp4", "a.mp3", "s.srt", "o.mp4", 0.0)


def test_build_cmd_maps_filtered_video_and_audio():
    cmd = build_cmd("vid.mp4", "output.mp3", "subtitles.srt", "out.mp4",
                    bg_offset=12.5)
    joined = " ".join(cmd)
    assert cmd[0] == "ffmpeg"
    assert "-ss 12.50" in joined          # seek before the video input
    assert joined.index("-ss") < joined.index("vid.mp4")
    assert "[0:v]" in joined and "[v]" in joined
    assert "-map [v] -map 1:a" in joined  # video from filter, audio from mp3
    assert "libx264" in joined
    assert "subtitles=subtitles.srt" in joined
    assert cmd[-1] == "out.mp4"
