"""Outbox with retry metadata: failed uploads park here and later --post
runs retry them (capped), so a bad cookie day heals itself over the schedule.

Each entry is <stem>.mp4 + <stem>.json (account, story, caption, attempts)
+ <stem>.txt (caption, for posting by hand). Files without a .json sidecar
are legacy/manual — never auto-retried.
"""

import json
import os
import shutil


def park(outbox_dir, video_src, meta) -> str:
    """Move a video into the outbox with sidecar + caption; returns the
    parked path. meta needs story_id, and part when it's a split part."""
    os.makedirs(outbox_dir, exist_ok=True)
    stem = meta["story_id"]
    if meta.get("part"):
        stem += f"_p{meta['part']}"
    parked = os.path.join(outbox_dir, stem + ".mp4")
    shutil.move(video_src, parked)
    meta = {**meta, "attempts": meta.get("attempts", 0)}
    with open(os.path.join(outbox_dir, stem + ".json"), "w",
              encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    with open(os.path.join(outbox_dir, stem + ".txt"), "w",
              encoding="utf-8") as f:
        f.write(meta.get("caption", ""))
    return parked


def entries(outbox_dir):
    """All sidecar-backed entries, oldest first (p1 before p2 in a tie).
    Ordered by VIDEO mtime — the sidecar is rewritten on every attempt bump,
    which would otherwise shuffle the retry order."""
    try:
        sidecars = [os.path.join(outbox_dir, n) for n in os.listdir(outbox_dir)
                    if n.endswith(".json")]
    except OSError:
        return []
    found = []
    for path in sidecars:
        try:
            with open(path, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        video = os.path.splitext(path)[0] + ".mp4"
        if os.path.exists(video):
            found.append((video, meta))
    return sorted(found, key=lambda e: (os.path.getmtime(e[0]), e[0]))


def next_retry(outbox_dir, account, max_attempts):
    """Oldest entry this account may retry, or None. A part 2 is held back
    while its part 1 is still parked — the sequel must not post first."""
    for video, meta in entries(outbox_dir):
        if (meta.get("account") != account
                or meta.get("attempts", 0) >= max_attempts):
            continue
        if meta.get("part") == 2:
            sibling = os.path.join(outbox_dir, f"{meta.get('story_id')}_p1.mp4")
            if os.path.exists(sibling):
                continue
        return video, meta
    return None


def bump_attempts(outbox_dir, video_path, meta) -> None:
    meta["attempts"] = meta.get("attempts", 0) + 1
    sidecar = os.path.splitext(video_path)[0] + ".json"
    with open(sidecar, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)


def clear(video_path) -> None:
    """Entry posted: drop video + sidecar + caption txt."""
    stem = os.path.splitext(video_path)[0]
    for p in (video_path, stem + ".json", stem + ".txt"):
        try:
            os.remove(p)
        except OSError:
            pass
