import os
import random
import subprocess

import pytest

import video
from video import build_chain_cmd, build_cmd, plan_background


def fake_probe(stdout):
    return lambda *a, **kw: subprocess.CompletedProcess(
        args=a, returncode=0, stdout=stdout, stderr="")


def make_theme(tmp_path, folder, names):
    d = tmp_path / folder
    d.mkdir()
    for n in names:
        (d / n).write_bytes(b"clip")


def prober(durs):
    return lambda p: durs[os.path.basename(p)]


def test_plan_horror_niche_uses_horror_folder(tmp_path):
    make_theme(tmp_path, "horror", ["cave.mp4"])
    make_theme(tmp_path, "scenic", ["beach.mp4"])
    plan = plan_background("horror", 10, rng=random.Random(1),
                           prober=prober({"cave.mp4": 60, "beach.mp4": 60}),
                           backgrounds_dir=str(tmp_path), fallback="vid.mp4")
    assert [os.path.basename(c) for c, _ in plan] == ["cave.mp4"]


def test_plan_other_niches_never_use_reserved_folders(tmp_path):
    for folder in ("horror", "abstract", "food", "scenic"):
        make_theme(tmp_path, folder, [f"{folder}.mp4"])
    durs = prober({f"{f}.mp4": 60 for f in ("horror", "abstract", "food", "scenic")})
    for seed in range(8):   # across seeds, drama never draws the horror theme
        plan = plan_background("drama", 10, rng=random.Random(seed), prober=durs,
                               backgrounds_dir=str(tmp_path), fallback="vid.mp4")
        assert "horror" not in plan[0][0]


def test_plan_single_clip_when_it_covers_narration(tmp_path):
    make_theme(tmp_path, "scenic", ["long.mp4"])
    plan = plan_background("drama", 30, rng=random.Random(1),
                           prober=prober({"long.mp4": 60.0}),
                           backgrounds_dir=str(tmp_path), fallback="vid.mp4")
    assert len(plan) == 1
    assert plan[0][1] == 60.0


def test_plan_chains_same_folder_until_covered(tmp_path):
    make_theme(tmp_path, "scenic", ["a.mp4", "b.mp4", "c.mp4"])
    durs = {"a.mp4": 12.0, "b.mp4": 12.0, "c.mp4": 12.0}
    plan = plan_background("drama", 30, rng=random.Random(2), prober=prober(durs),
                           backgrounds_dir=str(tmp_path), fallback="vid.mp4")
    assert len(plan) == 3   # 12 + 11.7 + 11.7 = 35.4 >= 31
    assert all(f"scenic{os.sep}" in c for c, _ in plan)
    covered = sum(d for _, d in plan) - 0.3 * (len(plan) - 1)
    assert covered >= 31


def test_plan_repeats_clips_when_folder_runs_short(tmp_path):
    make_theme(tmp_path, "scenic", ["a.mp4", "b.mp4"])
    plan = plan_background("drama", 40, rng=random.Random(3),
                           prober=prober({"a.mp4": 12.0, "b.mp4": 12.0}),
                           backgrounds_dir=str(tmp_path), fallback="vid.mp4")
    names = [os.path.basename(c) for c, _ in plan]
    assert len(names) >= 4          # needs ~4 x 12s for 41s of coverage
    assert len(set(names)) == 2     # only the two clips, repeated


def test_plan_empty_theme_tries_other_unreserved_then_loose(tmp_path):
    (tmp_path / "abstract").mkdir()                 # empty unreserved theme
    (tmp_path / "loose.mp4").write_bytes(b"clip")   # top-level, unreserved
    make_theme(tmp_path, "horror", ["cave.mp4"])    # reserved for horror
    plan = plan_background("drama", 10, rng=random.Random(1),
                           prober=prober({"loose.mp4": 60, "cave.mp4": 60}),
                           backgrounds_dir=str(tmp_path), fallback="vid.mp4")
    assert os.path.basename(plan[0][0]) == "loose.mp4"   # never the reserved clip


def test_plan_never_leaks_reserved_folder_even_as_last_resort(tmp_path):
    make_theme(tmp_path, "horror", ["cave.mp4"])    # only reserved folders exist
    make_theme(tmp_path, "drama", ["spat.mp4"])
    with pytest.raises(RuntimeError, match="no background clip"):
        plan_background("askreddit", 10, rng=random.Random(1),
                        prober=prober({"cave.mp4": 60, "spat.mp4": 60}),
                        backgrounds_dir=str(tmp_path),
                        fallback=str(tmp_path / "missing.mp4"))


def test_plan_empty_niche_folder_drops_to_unreserved(tmp_path):
    (tmp_path / "horror").mkdir()                   # niche folder exists, empty
    make_theme(tmp_path, "scenic", ["beach.mp4"])
    plan = plan_background("horror", 10, rng=random.Random(1),
                           prober=prober({"beach.mp4": 60}),
                           backgrounds_dir=str(tmp_path), fallback="vid.mp4")
    assert os.path.basename(plan[0][0]) == "beach.mp4"


def test_plan_falls_back_to_vid_then_errors(tmp_path):
    fallback = tmp_path / "vid.mp4"
    fallback.write_bytes(b"clip")
    plan = plan_background("drama", 10, rng=random.Random(1),
                           prober=prober({"vid.mp4": 60}),
                           backgrounds_dir=str(tmp_path / "none"),
                           fallback=str(fallback))
    assert plan == [(str(fallback), 60)]
    with pytest.raises(RuntimeError, match="no background clip"):
        plan_background("drama", 10, backgrounds_dir=str(tmp_path / "none"),
                        fallback=str(tmp_path / "missing.mp4"))


def test_plan_rejects_only_tiny_clips(tmp_path):
    make_theme(tmp_path, "scenic", ["blip.mp4"])
    with pytest.raises(RuntimeError, match="shorter"):
        plan_background("drama", 10, rng=random.Random(1),
                        prober=prober({"blip.mp4": 0.4}),
                        backgrounds_dir=str(tmp_path), fallback="vid.mp4")


def test_build_chain_cmd_crossfades_and_maps(tmp_path):
    chain = [("a.mp4", 12.0), ("b.mp4", 12.0), ("c.mp4", 12.0)]
    cmd = build_chain_cmd(chain, "output.mp3", "subtitles.srt", "out.mp4")
    joined = " ".join(cmd)
    assert cmd.count("-i") == 4                      # 3 clips + audio
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert fc.count("xfade") == 2                    # n-1 joins
    assert "offset=11.700" in fc and "offset=23.400" in fc
    assert fc.count("scale=1080:1920") == 3          # every clip normalized
    assert fc.count("subtitles=") == 1
    assert "-map [v] -map 3:a" in joined             # audio is input index n
    assert "-shortest" in joined


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


def test_build_cmd_with_ambient_loops_and_mixes_quietly():
    cmd = build_cmd("vid.mp4", "output.mp3", "subtitles.srt", "out.mp4",
                    bg_offset=0.0, ambient="drone.mp3", ambient_vol=0.12)
    joined = " ".join(cmd)
    assert "-stream_loop -1 -i drone.mp3" in joined
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "[2:a]volume=0.12" in fc              # bed is quiet
    assert "amix=inputs=2:duration=first:normalize=0" in fc
    assert "-map [v] -map [a]" in joined         # mixed audio, not the raw mp3


def test_build_chain_cmd_with_ambient_appends_input_after_audio():
    chain = [("a.mp4", 12.0), ("b.mp4", 12.0)]
    cmd = build_chain_cmd(chain, "output.mp3", "subtitles.srt", "out.mp4",
                          ambient="drone.mp3")
    joined = " ".join(cmd)
    assert cmd.count("-i") == 4                  # 2 clips + narration + ambient
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "[3:a]volume=" in fc                  # ambient is input n+1
    assert "[2:a][amb]amix" in fc                # mixed onto the narration
    assert "-map [v] -map [a]" in joined


def test_pick_ambient_uses_niche_folder_or_none(tmp_path):
    d = tmp_path / "horror"
    d.mkdir()
    (d / "drone.mp3").write_bytes(b"a")
    (d / "notes.txt").write_bytes(b"x")          # non-audio ignored
    got = video.pick_ambient("horror", ambient_dir=str(tmp_path),
                             rng=random.Random(1))
    assert os.path.basename(got) == "drone.mp3"
    assert video.pick_ambient("horror", ambient_dir=str(tmp_path / "no")) is None


def test_pick_ambient_falls_back_to_any_niche_folder(tmp_path):
    (tmp_path / "horror").mkdir()
    (tmp_path / "horror" / "drone.mp3").write_bytes(b"a")
    (tmp_path / "drama").mkdir()
    (tmp_path / "drama" / "piano.mp3").write_bytes(b"b")
    picks = {os.path.basename(video.pick_ambient(
                 "askreddit", ambient_dir=str(tmp_path), rng=random.Random(s)))
             for s in range(20)}
    assert picks == {"drone.mp3", "piano.mp3"}   # pool spans all folders


def test_pick_ambient_none_when_no_tracks_anywhere(tmp_path):
    (tmp_path / "horror").mkdir()                # folders exist but are empty
    assert video.pick_ambient("askreddit", ambient_dir=str(tmp_path)) is None


def test_cut_audio_builds_accurate_seek_cmd(monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0,
                                           stdout="", stderr="")

    monkeypatch.setattr(video.subprocess, "run", fake_run)
    video.cut_audio("output.mp3", "p1.mp3", 0.0, 58.25)
    joined = " ".join(seen["cmd"])
    assert joined.index("-i output.mp3") < joined.index("-ss")  # output-side seek
    assert "-t 58.250" in joined
    video.cut_audio("output.mp3", "p2.mp3", 58.25)
    assert "-t" not in seen["cmd"]               # tail slice runs to the end
