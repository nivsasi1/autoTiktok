import glob
import math
import os
import random
import subprocess

import config


def pick_background(backgrounds_dir=config.BACKGROUNDS_DIR,
                   fallback=config.INPUT_VID_PATH, rng=None) -> str:
    """A random clip from backgrounds_dir, else the single-clip fallback.

    Rotating clips (on top of the random start offset) is the main defense
    against TikTok's unoriginal-content flag on reused backgrounds.
    """
    rng = random if rng is None else rng
    clips = sorted(glob.glob(os.path.join(backgrounds_dir, "*.mp4")))
    if clips:
        return rng.choice(clips)
    if os.path.exists(fallback):
        return fallback
    raise RuntimeError(
        f"no background clip found — drop one or more .mp4 files in "
        f"{backgrounds_dir}/ (varied, watermark-free) or add a {fallback}.")


def build_cmd(vid, audio, srt, out, bg_offset,
              bitrate=config.VIDEO_BITRATE, force_style=config.FORCE_STYLE):
    # center-crop to 9:16 whatever the source resolution, then burn subtitles
    vf = (f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
          f"crop=1080:1920,subtitles={srt}:force_style='{force_style}'[v]")
    return ["ffmpeg", "-y",
            "-ss", f"{bg_offset:.2f}", "-i", vid,   # fast-seek the background
            "-i", audio,
            "-filter_complex", vf,
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-b:v", bitrate,
            "-c:a", "aac",
            "-shortest", out]


def get_duration(path: str) -> float:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {res.stderr.strip()}")
    try:
        duration = float(res.stdout.strip())
    except ValueError as exc:   # exit 0 but empty or "N/A" duration
        raise RuntimeError(
            f"ffprobe returned no duration for {path} "
            f"(got {res.stdout.strip()!r})") from exc
    # float() happily parses "nan"/"inf", which would poison pick_offset's
    # math (NaN comparisons are always False) and bake "-ss nan" into ffmpeg
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError(
            f"ffprobe returned a bogus duration for {path} "
            f"(got {res.stdout.strip()!r})")
    return duration


def pick_offset(vid_path: str, audio_path: str) -> float:
    """Random start into the background clip, leaving room for the narration."""
    vid_len = get_duration(vid_path)
    audio_len = get_duration(audio_path)
    max_offset = vid_len - audio_len - 1.0
    if max_offset <= 0:
        print(f"warning: {vid_path} ({vid_len:.0f}s) is shorter than the "
              f"narration ({audio_len:.0f}s); video will cut early")
        return 0.0
    return random.uniform(0.0, max_offset)


def export(vid, audio, srt, out, bg_offset) -> None:
    cmd = build_cmd(vid, audio, srt, out, bg_offset)
    # capture output so a scheduled/redirected run's failure names its cause
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        tail = "\n".join(res.stderr.strip().splitlines()[-8:])
        raise RuntimeError(
            "ffmpeg failed — is ffmpeg installed and on PATH, and do "
            f"{vid}/{audio}/{srt} all exist? (exit {res.returncode})\n"
            f"ffmpeg said:\n{tail}")
