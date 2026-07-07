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
import pipeline
import post_log
import video
from sources.askreddit import AskRedditSource
from sources.base import load_used_ids, record_used_id
from sources.reddit_text import RedditTextSource
from uploader.base import PostResult
from uploader.tiktok_cookies import CookieUploader, missing_cookies_error
from uploader.tiktok_profile import ProfileUploader


def build_source(niche: str, preset, used_ids):
    if niche == "askreddit":
        return AskRedditSource(preset, used_ids)
    return RedditTextSource(niche, preset, used_ids)


def _profile_dir(account_name: str) -> str:
    return os.path.join(config.PROFILES_DIR, account_name)


def _make_uploader(account_name: str):
    """Prefer the logged-in browser profile (survives TikTok's device-bound
    sessions); fall back to the cookies-file uploader."""
    pdir = _profile_dir(account_name)
    if os.path.isdir(pdir):
        return ProfileUploader(pdir, account_name)
    account = config.ACCOUNTS[account_name]
    return CookieUploader(account.cookies_file, account_name)


def _login(account_name: str) -> int:
    """Open the account's persistent browser profile for a one-time manual
    login; every later upload reuses it."""
    from playwright.sync_api import sync_playwright
    pdir = _profile_dir(account_name)
    os.makedirs(pdir, exist_ok=True)
    print(f"opening a browser — log into TikTok as '{account_name}' "
          "(google login is fine), then leave the window open…")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(pdir, channel="chrome",
                                                   headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.tiktok.com/login")
        deadline = time.time() + 300
        ok = False
        while time.time() < deadline:
            if any(c["name"] == "sessionid" for c in ctx.cookies()):
                ok = True
                break
            time.sleep(2)
        if ok:
            time.sleep(3)   # let post-login storage writes land
        ctx.close()
    if ok:
        print(f"logged in — profile saved under {pdir}; uploads for "
              f"'{account_name}' now use it automatically")
        return 0
    print("no login detected within 5 minutes — run it again")
    return 1


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
        uploader = _make_uploader(account_name)
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


def _park_part2(story_id) -> None:
    """Part 1 didn't go out: pull part 2 from the queue into the outbox so
    the scheduler can't post a sequel whose opener never appeared."""
    entry = pending.pop(config.QUEUE_DIR, story_id)
    if entry is None:
        return
    video_path, meta = entry
    os.makedirs(config.OUTBOX_DIR, exist_ok=True)
    parked = os.path.join(config.OUTBOX_DIR, os.path.basename(video_path))
    shutil.move(video_path, parked)
    Path(config.OUTBOX_DIR, f"{story_id}_p2.txt").write_text(
        meta.get("caption", ""), encoding="utf-8")
    print(f"part 1 failed — parked part 2 alongside it ({parked})")


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
    parser.add_argument("--login", action="store_true",
                        help="one-time manual TikTok login into the account's "
                             "persistent browser profile")
    args = parser.parse_args()

    if args.login:
        if not args.account:
            parser.error("--login requires --account")
        return _login(args.account)

    if args.post:
        if not args.account:
            parser.error("--post requires --account")
        account = config.ACCOUNTS[args.account]
        niche = account.niche
        if (not args.dry_run
                and not os.path.isdir(_profile_dir(args.account))
                and not os.path.exists(account.cookies_file)):
            print("error: " + missing_cookies_error(account.cookies_file,
                                                    args.account))
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

    result = pipeline.render_story(story, preset, niche)

    try:
        record_used_id(config.STATE_PATH, story.id)
    except OSError as exc:
        # the video is already rendered — don't lose it over a state hiccup
        print(f"warning: couldn't update {config.STATE_PATH} ({exc}); "
              "this story may be picked again next run")

    if args.post:
        if result.split:
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
            rc = _publish(story, args.account, args.dry_run, part=1)
            if rc != 0 and not args.dry_run:
                _park_part2(story.id)
            return rc
        return _publish(story, args.account, args.dry_run)
    if result.split:
        print(f"done -> {config.OUTPUT_VID_PATH} + {config.OUTPUT_PART2_PATH}")
    else:
        print(f"done -> {config.OUTPUT_VID_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
