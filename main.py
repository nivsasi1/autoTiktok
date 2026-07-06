import argparse
import os
import random
import shutil
import sys
import time
from pathlib import Path

import config
import metadata
import post_log
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


def _publish(story, account_name: str, dry_run: bool) -> int:
    """Caption + upload the rendered video; park it in the outbox on failure."""
    account = config.ACCOUNTS[account_name]
    caption = metadata.build_caption(story, account.niche)
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "account": account_name,
              "niche": account.niche, "story_id": story.id, "title": story.title,
              "url": story.url}
    if dry_run:
        print(f"dry-run: would post {config.OUTPUT_VID_PATH}")
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
        result = uploader.upload(config.OUTPUT_VID_PATH, caption)
    except Exception as exc:
        result = PostResult(False, f"{exc.__class__.__name__}: {exc}")
    try:
        post_log.append_post(config.POST_LOG_PATH,
                             {**record, "ok": result.ok, "detail": result.detail})
    except OSError as exc:
        print(f"warning: couldn't write {config.POST_LOG_PATH} ({exc})")
    if not result.ok:
        os.makedirs(config.OUTBOX_DIR, exist_ok=True)
        parked = os.path.join(config.OUTBOX_DIR, f"{story.id}.mp4")
        shutil.move(config.OUTPUT_VID_PATH, parked)
        Path(config.OUTBOX_DIR, f"{story.id}.txt").write_text(
            caption, encoding="utf-8")
        print(f"upload failed ({result.detail}); video parked at {parked}")
        return 1
    print(f"posted to {account_name}: {caption[:60]}")
    return 0


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
    else:
        niche = args.niche or config.DEFAULT_NICHE
    preset = config.NICHES[niche]

    try:
        video.plan_background(niche, 0)   # fail fast: any usable clip at all?
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

    subtitles.write_srt(boundaries, config.SRT_PATH, preset.words_per_line)
    print(f"subtitles: {config.SRT_PATH} ({preset.words_per_line} words/line)")

    narration = video.get_duration(config.AUDIO_PATH)
    chain = video.plan_background(niche, narration)
    if len(chain) == 1:
        clip, dur = chain[0]
        offset = random.uniform(0.0, max(dur - narration - 1.0, 0.0))
        print(f"render: {os.path.basename(clip)} @ offset {offset:.1f}s")
        video.export(clip, config.AUDIO_PATH, config.SRT_PATH,
                     config.OUTPUT_VID_PATH, offset)
    else:
        names = ", ".join(os.path.basename(c) for c, _ in chain)
        print(f"render: {len(chain)}-clip crossfade chain ({names})")
        video.export(chain, config.AUDIO_PATH, config.SRT_PATH,
                     config.OUTPUT_VID_PATH)

    try:
        record_used_id(config.STATE_PATH, story.id)
    except OSError as exc:
        # the video is already rendered — don't lose it over a state hiccup
        print(f"warning: couldn't update {config.STATE_PATH} ({exc}); "
              "this story may be picked again next run")

    if args.post:
        return _publish(story, args.account, args.dry_run)
    print(f"done -> {config.OUTPUT_VID_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
