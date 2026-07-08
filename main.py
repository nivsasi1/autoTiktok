import argparse
import os
import random
import subprocess
import sys
import time
from types import SimpleNamespace

import config
import metadata
import notify
import outbox
import pending
import pipeline
import post_log
import video
from sources.askreddit import AskRedditSource
from sources.base import load_used_ids, record_used_id
from sources.reddit_text import RedditTextSource
from uploader.base import PostResult
from uploader.tiktok_cookies import CookieUploader, missing_cookies_error
from uploader.tiktok_profile import (ProfileUploader, find_chrome,
                                     profile_logged_in)


def build_source(niche: str, preset, used_ids):
    if niche == "askreddit":
        return AskRedditSource(preset, used_ids)
    return RedditTextSource(niche, preset, used_ids)


def _profile_dir(account_name: str) -> str:
    return os.path.join(config.PROFILES_DIR, account_name)


def _make_uploader(account_name: str):
    """Prefer a VERIFIED logged-in browser profile (survives TikTok's
    device-bound sessions); fall back to the cookies-file uploader."""
    pdir = _profile_dir(account_name)
    if profile_logged_in(pdir):
        return ProfileUploader(pdir, account_name)
    account = config.ACCOUNTS[account_name]
    if os.path.exists(account.cookies_file):
        return CookieUploader(account.cookies_file, account_name)
    # no cookies either: the profile uploader's error names the fix
    return ProfileUploader(pdir, account_name)


def _login(account_name: str) -> int:
    """One-time manual login in a PLAIN Chrome on the account's profile dir.
    No automation attached: Google's OAuth refuses controlled browsers and
    TikTok rate-limits logins in them — a normal window sails through.
    Uploads then reuse the same profile via Playwright."""
    pdir = os.path.abspath(_profile_dir(account_name))
    os.makedirs(pdir, exist_ok=True)
    chrome = find_chrome()
    if chrome is None:
        print("error: couldn't find chrome.exe — install Google Chrome")
        return 1
    print(f"opening Chrome — log into TikTok as '{account_name}' (google "
          "login works in this window), then CLOSE the window to finish")
    subprocess.run([chrome, f"--user-data-dir={pdir}", "--no-first-run",
                    "--no-default-browser-check", "--new-window",
                    "https://www.tiktok.com/login"])
    if profile_logged_in(pdir):
        print(f"logged in — uploads for '{account_name}' now use the "
              f"profile under {pdir} automatically")
        return 0
    print("login not detected — did the window close before you finished? "
          "run it again")
    return 1


def _publish(story, account_name: str, dry_run: bool,
             part=None, video_path=None, caption=None,
             park_on_fail=True) -> int:
    """Caption + upload the rendered video; park it in the outbox on failure
    (park_on_fail=False when the video already lives in the outbox)."""
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
        if park_on_fail:
            meta = {"story_id": story.id, "account": account_name,
                    "niche": account.niche, "title": story.title,
                    "url": story.url, "caption": caption}
            if part:
                meta["part"] = part
            parked = outbox.park(config.OUTBOX_DIR, video_path, meta)
            print(f"upload failed ({result.detail}); video parked at {parked}"
                  f" — later --post runs retry it "
                  f"(up to {config.MAX_UPLOAD_RETRIES}x)")
            plan = (f"parked at {parked} — later scheduled runs retry it "
                    f"automatically (up to {config.MAX_UPLOAD_RETRIES}x).")
        else:
            print(f"upload failed ({result.detail})")
            plan = "this was a retry of a parked video — see --status."
        notify.send_failure(
            f"upload failed for {account_name}",
            f"{story.title}\n\nreason: {result.detail}\n\n{plan}")
        return 1
    print(f"posted to {account_name}: {caption[:60]}")
    return 0


def _publish_outbox(account_name: str, dry_run: bool):
    """Retry the oldest parked upload for this account; None if nothing to
    retry. A dry run reports the entry but changes nothing."""
    entry = outbox.next_retry(config.OUTBOX_DIR, account_name,
                              config.MAX_UPLOAD_RETRIES)
    if entry is None:
        return None
    video_path, meta = entry
    attempt = meta.get("attempts", 0) + 1
    print(f"outbox retry {attempt}/{config.MAX_UPLOAD_RETRIES}: "
          f"{os.path.basename(video_path)} ({meta.get('title', '')[:50]})")
    story = SimpleNamespace(id=meta.get("story_id"), title=meta.get("title"),
                            url=meta.get("url"))
    rc = _publish(story, account_name, dry_run, part=meta.get("part"),
                  video_path=video_path, caption=meta.get("caption"),
                  park_on_fail=False)
    if dry_run:
        return rc
    if rc == 0:
        outbox.clear(video_path)
    else:
        outbox.bump_attempts(config.OUTBOX_DIR, video_path, meta)
        if attempt >= config.MAX_UPLOAD_RETRIES:
            print(f"retries exhausted for {os.path.basename(video_path)} — "
                  "post it by hand (see --status)")
            notify.send_failure(
                f"action needed: retries exhausted "
                f"({os.path.basename(video_path)})",
                f"{meta.get('title', '')}\n\nall "
                f"{config.MAX_UPLOAD_RETRIES} automatic retries failed — "
                f"post it by hand (caption sits next to the video in "
                f"{config.OUTBOX_DIR}/). run `python main.py --status` "
                "for the full picture.")
    return rc


def _park_part2(story_id) -> None:
    """Part 1 didn't go out: pull part 2 from the queue into the outbox so
    the scheduler can't post a sequel whose opener never appeared. The pair
    retries in order (p1 before p2) on later runs."""
    entry = pending.pop(config.QUEUE_DIR, story_id)
    if entry is None:
        return
    video_path, meta = entry
    parked = outbox.park(config.OUTBOX_DIR, video_path, meta)
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


def _status() -> int:
    """One-glance system state: auth, queue, outbox, recent posts."""
    print("accounts:")
    for name, acc in sorted(config.ACCOUNTS.items()):
        if profile_logged_in(_profile_dir(name)):
            auth = "browser profile: logged in"
        elif os.path.exists(acc.cookies_file):
            auth = ("cookies file only (may bounce off ticket guard) — "
                    f"better: python main.py --login --account {name}")
        else:
            auth = f"NO LOGIN — run: python main.py --login --account {name}"
        print(f"  {name} [{acc.niche}]: {auth}")

    queued = pending.entries(config.QUEUE_DIR)
    print(f"\nqueue ({len(queued)}):")
    for _video, meta in queued:
        print(f"  part {meta.get('part')} for {meta.get('account')}: "
              f"{meta.get('title', '')[:60]}")

    parked = outbox.entries(config.OUTBOX_DIR)
    print(f"\noutbox ({len(parked)}):")
    for video_path, meta in parked:
        attempts = meta.get("attempts", 0)
        state = ("auto-retry pending"
                 if attempts < config.MAX_UPLOAD_RETRIES
                 else "retries exhausted — post by hand")
        print(f"  {os.path.basename(video_path)} ({meta.get('account')}, "
              f"attempts {attempts}/{config.MAX_UPLOAD_RETRIES}): {state}")
    try:   # legacy parks without sidecars are manual-only
        known = {os.path.basename(v) for v, _ in parked}
        for n in sorted(os.listdir(config.OUTBOX_DIR)):
            if n.endswith(".mp4") and n not in known:
                print(f"  {n}: no metadata — post by hand")
    except OSError:
        pass

    posts = post_log.read_posts(config.POST_LOG_PATH)[-5:]
    print(f"\nlast posts ({len(posts)}):")
    for rec in posts:
        ok = {True: "ok", False: "FAILED", None: "dry-run/no-op"}[rec.get("ok")]
        print(f"  {rec.get('ts', '?')} {rec.get('account')}: {ok} — "
              f"{(rec.get('title') or rec.get('detail') or '')[:60]}")
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
    parser.add_argument("--now", action="store_true",
                        help="with --post: skip the 0-15 min anti-bot delay "
                             "(for watched manual runs)")
    parser.add_argument("--login", action="store_true",
                        help="one-time manual TikTok login into the account's "
                             "persistent browser profile")
    parser.add_argument("--status", action="store_true",
                        help="show auth, queue, outbox and recent posts")
    args = parser.parse_args()

    if args.status:
        return _status()

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
                and not profile_logged_in(_profile_dir(args.account))
                and not os.path.exists(account.cookies_file)):
            print(f"error: no login for '{args.account}' — run: python "
                  f"main.py --login --account {args.account}\n(or, fallback: "
                  + missing_cookies_error(account.cookies_file,
                                          args.account) + ")")
            return 1
        if not args.dry_run and not args.now:
            # human-irregular timing on top of Task Scheduler's random delay
            delay = random.uniform(0, config.POST_JITTER_MAX_S)
            print(f"jitter: waiting {delay / 60:.1f} min before posting "
                  "(skip with --now)", flush=True)
            time.sleep(delay)
        # a queued part 2 goes out before anything new is fetched/rendered,
        # then parked failures get their retry — one post per run either way
        queued_rc = _publish_queued(args.account, args.dry_run)
        if queued_rc is not None:
            return queued_rc
        outbox_rc = _publish_outbox(args.account, args.dry_run)
        if outbox_rc is not None:
            return outbox_rc
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
    try:
        sys.exit(main())
    except Exception:
        # a scheduled run that dies unseen is worse than the failure itself
        import traceback
        notify.send_failure("run crashed", traceback.format_exc())
        raise
