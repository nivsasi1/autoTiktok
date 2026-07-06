"""Part-2 queue: a --post run posts a queued part before fetching anything new,
so a split story goes out as two consecutive scheduled posts."""

import json
import os
import shutil


def enqueue(queue_dir, video_src, meta) -> str:
    """Move a rendered part into the queue with a JSON sidecar; returns the
    queued video path."""
    os.makedirs(queue_dir, exist_ok=True)
    stem = f"{meta['story_id']}_p{meta['part']}"
    video_dst = os.path.join(queue_dir, stem + ".mp4")
    shutil.move(video_src, video_dst)
    with open(os.path.join(queue_dir, stem + ".json"), "w",
              encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    return video_dst


def next_entry(queue_dir, account):
    """Oldest queued (video_path, meta) for `account`, or None."""
    try:
        sidecars = [os.path.join(queue_dir, n) for n in os.listdir(queue_dir)
                    if n.endswith(".json")]
    except OSError:
        return None
    for path in sorted(sidecars, key=os.path.getmtime):
        try:
            with open(path, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue   # corrupt sidecar: skip, don't block the queue
        video = os.path.splitext(path)[0] + ".mp4"
        if meta.get("account") == account and os.path.exists(video):
            return video, meta
    return None


def pop(queue_dir, story_id, part=2):
    """Take a specific entry out of the queue (video_path, meta) — used to
    pull part 2 back when part 1's upload fails. None if not queued."""
    stem = os.path.join(queue_dir, f"{story_id}_p{part}")
    video, sidecar = stem + ".mp4", stem + ".json"
    if not os.path.exists(video):
        return None
    try:
        with open(sidecar, encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        meta = {}
    try:
        os.remove(sidecar)
    except OSError:
        pass
    return video, meta


def remove(video_path) -> None:
    """Drop an entry once posted (or parked): sidecar always, video if the
    publish path didn't already move it away."""
    sidecar = os.path.splitext(video_path)[0] + ".json"
    for p in (sidecar, video_path):
        try:
            os.remove(p)
        except OSError:
            pass
