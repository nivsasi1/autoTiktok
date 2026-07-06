import glob
import math
import os
import random
import subprocess

import config


def _candidate_clips(backgrounds_dir, niche, rng):
    """One theme folder's clips: the folder named after the niche wins; else a
    random unreserved folder (a folder named after ANY niche is reserved for
    it and never serves another niche); else loose top-level clips."""
    try:
        subs = sorted(e.name for e in os.scandir(backgrounds_dir) if e.is_dir())
    except OSError:
        subs = []

    def folder_clips(name):
        return sorted(glob.glob(os.path.join(backgrounds_dir, name, "*.mp4")))

    if niche in subs:
        clips = folder_clips(niche)
        if clips:
            return clips
    unreserved = [s for s in subs if s not in config.NICHES]
    rng.shuffle(unreserved)
    for sub in unreserved:      # random folder, skipping empty ones
        clips = folder_clips(sub)
        if clips:
            return clips
    return sorted(glob.glob(os.path.join(backgrounds_dir, "*.mp4")))


def plan_background(niche, needed, rng=None, prober=None,
                    backgrounds_dir=config.BACKGROUNDS_DIR,
                    fallback=config.INPUT_VID_PATH):
    """Plan clips covering `needed` seconds from one theme folder.

    Returns [(path, duration), ...]. One clip if it covers the narration;
    otherwise a shuffled same-folder chain (crossfaded joins each cost
    CROSSFADE_S of coverage; clips repeat once a small folder runs dry).
    Rotating varied clips is the main defense against TikTok's
    unoriginal-content flag on reused backgrounds.
    """
    rng = random if rng is None else rng
    prober = get_duration if prober is None else prober
    clips = _candidate_clips(backgrounds_dir, niche, rng)
    if not clips:
        if os.path.exists(fallback):
            clips = [fallback]
        else:
            raise RuntimeError(
                f"no background clip found — drop .mp4 files (ideally in theme "
                f"subfolders) under {backgrounds_dir}/ or add a {fallback}.")

    durations = {c: prober(c) for c in clips}
    usable = [c for c in clips if durations[c] > config.CROSSFADE_S * 2]
    if not usable:
        raise RuntimeError(
            f"background clips under {os.path.dirname(clips[0])} are all shorter "
            f"than {config.CROSSFADE_S * 2:.1f}s — add longer clips.")

    target = needed + config.CHAIN_BUFFER_S
    first = rng.choice(usable)
    if durations[first] >= target:
        return [(first, durations[first])]

    chain, covered, deck = [], 0.0, []
    while covered < target:
        if not deck:
            deck = usable[:]
            rng.shuffle(deck)
        clip = deck.pop()
        fade = config.CROSSFADE_S if chain else 0.0
        chain.append((clip, durations[clip]))
        covered += durations[clip] - fade
    return chain


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


def build_chain_cmd(chain, audio, srt, out,
                    bitrate=config.VIDEO_BITRATE,
                    force_style=config.FORCE_STYLE, fade=None):
    """Chain of clips: each normalized to 1080x1920@30, crossfaded joins,
    subtitles burned over the whole run. One render pass, no temp files."""
    fade = config.CROSSFADE_S if fade is None else fade
    cmd = ["ffmpeg", "-y"]
    for clip, _ in chain:
        cmd += ["-i", clip]
    cmd += ["-i", audio]
    n = len(chain)
    parts = [
        (f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
         f"crop=1080:1920,fps=30,setsar=1,format=yuv420p,"
         f"setpts=PTS-STARTPTS[v{i}]")
        for i in range(n)
    ]
    cur, total = "[v0]", chain[0][1]
    for i in range(1, n):
        off = total - fade
        parts.append(f"{cur}[v{i}]xfade=transition=fade:"
                     f"duration={fade:.2f}:offset={off:.3f}[x{i}]")
        cur, total = f"[x{i}]", off + chain[i][1]
    parts.append(f"{cur}subtitles={srt}:force_style='{force_style}'[v]")
    return cmd + ["-filter_complex", ";".join(parts),
                  "-map", "[v]", "-map", f"{n}:a",
                  "-c:v", "libx264", "-preset", "fast", "-b:v", bitrate,
                  "-c:a", "aac", "-shortest", out]


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


def export(background, audio, srt, out, bg_offset=0.0) -> None:
    """background: a single clip path (with bg_offset), or a [(clip, dur), ...]
    chain from plan_background (crossfaded, offset ignored)."""
    if isinstance(background, list) and len(background) > 1:
        cmd = build_chain_cmd(background, audio, srt, out)
    else:
        vid = background[0][0] if isinstance(background, list) else background
        cmd = build_cmd(vid, audio, srt, out, bg_offset)
    # capture output so a scheduled/redirected run's failure names its cause
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        tail = "\n".join(res.stderr.strip().splitlines()[-8:])
        raise RuntimeError(
            "ffmpeg failed — is ffmpeg installed and on PATH, and do "
            f"{vid}/{audio}/{srt} all exist? (exit {res.returncode})\n"
            f"ffmpeg said:\n{tail}")
