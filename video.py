import random
import subprocess

import config


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
    return float(res.stdout.strip())


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
    res = subprocess.run(cmd)
    if res.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed — is ffmpeg installed and on PATH, and do "
            f"{vid}/{audio}/{srt} all exist? (exit {res.returncode})")
