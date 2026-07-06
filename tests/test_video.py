import subprocess

import pytest

import video
from video import build_cmd


def fake_probe(stdout):
    return lambda *a, **kw: subprocess.CompletedProcess(
        args=a, returncode=0, stdout=stdout, stderr="")


def test_get_duration_parses_ffprobe_output(monkeypatch):
    monkeypatch.setattr(video.subprocess, "run", fake_probe("12.34\n"))
    assert video.get_duration("clip.mp4") == 12.34


@pytest.mark.parametrize("stdout", ["", "N/A\n"])
def test_get_duration_raises_runtime_error_on_unparsable_output(monkeypatch, stdout):
    monkeypatch.setattr(video.subprocess, "run", fake_probe(stdout))
    with pytest.raises(RuntimeError, match=r"ffprobe.*clip\.mp4"):
        video.get_duration("clip.mp4")


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
