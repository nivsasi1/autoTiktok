import argparse
import os
import random
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import config
import metadata
import pending
import post_log
import split
import subtitles
import tts
import video
from sources.askreddit import AskRedditSource
from sources.base import load_used_ids, record_used_id
from sources.reddit_text import RedditTextSource
from uploader.base import PostResult
from uploader.tiktok_cookies import CookieUploader


def build_source(niche: str, preset, used_ids):
    if niche == "askreddit":
        return AskRedditSource(preset, used_ids)
    return RedditTextSource(niche, preset, used_ids)


def _publish(story, account_name: str, dry_run: bool,
             part=None, video_path=None, caption=None) -> int:
    """Caption + upload the rendered video; park it in the outbox on failure."""
    account = config.ACCOUNTS[account_name]
    video_path = config.OUTPUT_VID_PATH if video_path is None else video_path
    if caption is None:
        caption = metadata.build_caption(story, account.niche, part=part)
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "account": account_name,
              "niche": account.niche, "story_id": story.id, "title": story.title,
              "url": story.url}
    if part:
        record["part"] = part
    if dry_run:
        print(f"dry-run: would post {video_path}")
        print(f"caption: {caption}")
        try:
            post_log.append_post(config.POST_LOG_PATH,
                                 {**record, "ok": None, "detail": "dry-run"})
        except OSError as exc:
            print(f"warning: couldn't write {config.POST_LOG_PATH} ({exc})")
        return 0
    try:
        # a missing/locked cookies file raises in the constructor; catch it so
        # the rendered video is parked in the outbox, not stranded by a crash
        uploader = CookieUploader(account.cookies_file, account_name)
        result = uploader.upload(video_path, caption)
    except Exception as exc:
        result = PostResult(False, f"{exc.__class__.__name__}: {exc}")
    try:
        post_log.append_post(config.POST_LOG_PATH,
                             {**record, "ok": result.ok, "detail": result.detail})
    except OSError as exc:
        print(f"warning: couldn't write {config.POST_LOG_PATH} ({exc})")
    if not result.ok:
        os.makedirs(config.OUTBOX_DIR, exist_ok=True)
        stem = f"{story.id}_p{part}" if part else story.id
        parked = os.path.join(config.OUTBOX_DIR, f"{stem}.mp4")
        shutil.move(video_path, parked)
        Path(config.OUTBOX_DIR, f"{stem}.txt").write_text(
            caption, encoding="utf-8")
        print(f"upload failed ({result.detail}); video parked at {parked}")
        return 1
    print(f"posted to {account_name}: {caption[:60]}")
    return 0


def _publish_queued(account_name: str, dry_run: bool):
    """Post the oldest queued part for this account; None if queue is empty.
    A dry run reports the entry but leaves it queued."""
    entry = pending.next_entry(config.QUEUE_DIR, account_name)
    if entry is None:
        return None
    video_path, meta = entry
    print(f"queued part {meta.get('part')}: {meta.get('title')}")
    story = SimpleNamespace(id=meta.get("story_id"), title=meta.get("title"),
                            url=meta.get("url"))
    rc = _publish(story, account_name, dry_run, part=meta.get("part"),
                  video_path=video_path, caption=meta.get("caption"))
    if not dry_run:
        pending.remove(video_path)
    return rc


def _part_path(base: str, n: int) -> str:
    root, ext = os.path.splitext(base)
    return f"{root}_part{n}{ext}"


def _render(niche: str, audio_path: str, srt_path: str, out_path: str) -> None:
    """Plan a background for this narration and export one video."""
    narration = video.get_duration(audio_path)
    chain = video.plan_background(niche, narration)
    ambient = video.pick_ambient(niche)
    if ambient:
        print(f"ambient: {os.path.basename(ambient)}")
    if len(chain) == 1:
        clip, dur = chain[0]
        if dur < narration + 1.0:
            print(f"warning: {os.path.basename(clip)} ({dur:.0f}s) barely covers "
                  f"the narration ({narration:.0f}s); video may cut early")
        offset = random.uniform(0.0, max(dur - narration - 1.0, 0.0))
        print(f"render: {os.path.basename(clip)} @ offset {offset:.1f}s")
        video.export(clip, audio_path, srt_path, out_path, offset,
                     ambient=ambient)
    else:
        names = ", ".join(os.path.basename(c) for c, _ in chain)
        print(f"render: {len(chain)}-clip crossfade chain ({names})")
        video.export(chain, audio_path, srt_path, out_path, ambient=ambient)


def main() -> int:
    # redirected stdout defaults to cp1252 on Windows; emoji in story titles
    # would crash prints once a scheduler logs to a file
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Reddit story -> TikTok video")
    parser.add_argument("--niche", choices=sorted(config.NICHES))
    parser.add_argument("--post", action="store_true",
                        help="upload to TikTok after rendering")
    parser.add_argument("--account", choices=sorted(config.ACCOUNTS),
                        help="account to post as (implies its niche)")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --post: render and caption, skip the upload")
    args = parser.parse_args()

    if args.post:
        if not args.account:
            parser.error("--post requires --account")
        account = config.ACCOUNTS[args.account]
        niche = account.niche
        if not args.dry_run and not os.path.exists(account.cookies_file):
            print(f"error: cookies file {account.cookies_file} for "
                  f"'{args.account}' missing — see README 'Cookie export'")
            return 1
        if not args.dry_run:
            # human-irregular timing on top of Task Scheduler's random delay
            time.sleep(random.uniform(0, config.POST_JITTER_MAX_S))
        # a queued part 2 goes out before anything new is fetched/rendered
        queued_rc = _publish_queued(args.account, args.dry_run)
        if queued_rc is not None:
            return queued_rc
    else:
        niche = args.niche or config.DEFAULT_NICHE
    preset = config.NICHES[niche]

    try:
        # fail fast: any clip at all? (durations don't matter yet — stub the
        # prober so this doesn't ffprobe every clip twice per run)
        video.plan_background(niche, 0, prober=lambda _: 999.0)
    except RuntimeError as exc:
        print(f"error: {exc}")
        return 1

    used_ids = load_used_ids(config.STATE_PATH)
    story = build_source(niche, preset, used_ids).fetch()
    if story is None:
        print(f"no qualifying {niche} post right now — try again later")
        if args.post:
            # keep posts.jsonl a full cadence audit: a dry subreddit day is
            # distinct from a scheduler that never fired
            try:
                post_log.append_post(config.POST_LOG_PATH, {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "account": args.account, "niche": niche,
                    "story_id": None, "ok": None, "detail": "no story"})
            except OSError as exc:
                print(f"warning: couldn't write {config.POST_LOG_PATH} ({exc})")
        return 0
    print(f"story: {story.title}\n       {story.url}")

    print(f"tts: {preset.voice}, {len(story.text)} chars")
    boundaries = tts.synthesize(story.text, config.AUDIO_PATH, preset.voice)

    narration = video.get_duration(config.AUDIO_PATH)
    split_plan = None
    if narration > config.SPLIT_THRESHOLD_S:
        split_plan = split.split_boundaries(boundaries, narration)

    if split_plan:
        cut, part1, part2 = split_plan
        print(f"split: {narration:.0f}s narration -> part 1 ({cut:.0f}s) "
              f"+ part 2 ({narration - cut:.0f}s)")
        parts = [(1, part1, 0.0, cut, config.OUTPUT_VID_PATH),
                 (2, part2, cut, None, config.OUTPUT_PART2_PATH)]
        for n, bounds, start, dur, out_path in parts:
            part_audio = _part_path(config.AUDIO_PATH, n)
            part_srt = _part_path(config.SRT_PATH, n)
            video.cut_audio(config.AUDIO_PATH, part_audio, start, dur)
            part_len = cut if n == 1 else narration - cut
            subtitles.write_srt(bounds, part_srt, preset.words_per_line,
                                extra_cues=split.label_cues(n, part_len))
            _render(niche, part_audio, part_srt, out_path)
    else:
        subtitles.write_srt(boundaries, config.SRT_PATH, preset.words_per_line)
        print(f"subtitles: {config.SRT_PATH} ({preset.words_per_line} words/line)")
        _render(niche, config.AUDIO_PATH, config.SRT_PATH,
                config.OUTPUT_VID_PATH)

    try:
        record_used_id(config.STATE_PATH, story.id)
    except OSError as exc:
        # the video is already rendered — don't lose it over a state hiccup
        print(f"warning: couldn't update {config.STATE_PATH} ({exc}); "
              "this story may be picked again next run")

    if args.post:
        if split_plan:
            # queue part 2 before touching the upload so a crash can't lose it
            caption2 = metadata.build_caption(story, niche, part=2)
            if args.dry_run:
                print(f"dry-run: would queue {config.OUTPUT_PART2_PATH} "
                      f"for the next run")
            else:
                pending.enqueue(config.QUEUE_DIR, config.OUTPUT_PART2_PATH,
                                {"story_id": story.id, "part": 2,
                                 "account": args.account, "niche": niche,
                                 "title": story.title, "url": story.url,
                                 "caption": caption2})
            return _publish(story, args.account, args.dry_run, part=1)
        return _publish(story, args.account, args.dry_run)
    if split_plan:
        print(f"done -> {config.OUTPUT_VID_PATH} + {config.OUTPUT_PART2_PATH}")
    else:
        print(f"done -> {config.OUTPUT_VID_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
