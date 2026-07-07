# autoTiktok

Reddit story → TTS narration → vertical video with perfectly-synced captions,
ready for TikTok. Three built-in niches: **drama** (AITA, revenge, TIFU),
**horror** (nosleep & co., word-pop captions), **askreddit** (question + top
answers).

## Setup

1. **Python deps** (3.10+):
   ```
   pip install -r requirements.txt
   ```
2. **ffmpeg** (includes ffprobe):
   ```
   winget install Gyan.FFmpeg
   ```
   (new terminal afterwards so PATH refreshes)
3. **(Optional) User-Agent** — no credentials needed; Reddit's public RSS
   feeds just want a descriptive UA. The default works, but to set your own:
   ```
   copy .env.example .env    # REDDIT_USER_AGENT=autoTiktok/1.0 by u/<you>
   ```
4. **Background clips** — drop one or more `.mp4` files in `assets/backgrounds/`.
   Each render picks a random clip at a random start offset, so no two videos
   look alike. (A single `vid.mp4` in the repo root still works as a fallback.)

   **This matters for reach.** TikTok's originality filter flags reused
   backgrounds — the ubiquitous Minecraft parkour / Subway Surfers / GTA clips
   are heavily fingerprinted and will get videos throttled. Use **varied,
   watermark-free, less-common** footage (satisfying/aesthetic loops, your own
   recordings). Longer clips give the random offset more room to vary.
5. **(Optional) Ambient beds** — drop audio files (`.mp3`/`.m4a`/`.wav`/`.ogg`)
   in `assets/ambient/<niche>/` and each render loops a random one quietly
   under the narration (`AMBIENT_VOLUME` in `config.py`). Niches without
   their own tracks borrow a random bed from the other niche folders; with
   no tracks at all it's plain narration (like the clips, `assets/` stays
   out of git).
   Royalty-free ambience only — TikTok mutes videos over copyright audio.

## Usage

```
python main.py                      # default niche (drama)
python main.py --niche horror
python main.py --niche askreddit
```

Output: `out.mp4` (1080x1920, karaoke captions burned in — spoken words sweep
to yellow, timed from real TTS word boundaries — plus a Reddit-post-style
hook card over the first 3s: the niche account's avatar (`assets/pfp_<account>.png`),
handle, title and engagement row; falls back to a big text hook if card
rendering fails). Artifacts `output.mp3` / `captions.ass` are left behind for
inspection; `state.json` remembers used posts so you never render the same
story twice.

Narrations over `SPLIT_THRESHOLD_S` (100s) are split at a mid-story sentence
end into **Part 1/2 + Part 2/2** — on-screen labels, a TO BE CONTINUED tease,
part-labelled captions, and part 2 opens with a spoken "Part 2 of \<title\>"
lead-in so it never resumes mid-thought. Without `--post` both land next to
each other (`out.mp4` + `out_part2.mp4`); with `--post`, part 1 posts now and
part 2 waits in `queue/` — the next scheduled run posts it before fetching
anything new, so a split story goes out as two consecutive posts. If part 1's
upload fails, part 2 is parked in `outbox/` alongside it instead of staying
scheduled.

Niche presets (subreddits, voice, words-per-caption, outro) live in
`config.py` — edit them freely.

## GUI (Phase C)

```
python gui.py
```

Opens a local Gradio app (127.0.0.1 only): pick a source — **auto** (niche
feed), **reddit url** (paste any selftext post), or **freeform** (your own
title + text) — choose niche and voice, hit **Render**, watch the status
stream, preview the video (both parts when split), tweak the caption, then
**Post** (dry-run by default). Split stories queue part 2 for the scheduler
exactly like the CLI.

## Tests

```
python -m pytest tests/ -v
```

## Auto-posting (Phase B)

**Risk, stated plainly:** upload uses browser cookies + automation
(`tiktok-uploader`), which violates TikTok's ToS. Detection risk is mitigated
(randomized times, modest cadence) but never zero. The official API swaps in
once its audit is approved.

### One-time setup per account
```
python main.py --login --account redditregrets
```
A browser opens — log into TikTok as that account (Google login works) and
wait for the confirmation. The login lives in a persistent browser profile
under `profiles/<account>/` that every upload reuses.

**Why not just cookies?** TikTok binds web sessions to device keys stored in
the original browser (ticket guard), so a `cookies.txt` export bounces to the
login page when replayed elsewhere. A cookies file at
`cookies/<account>.txt` still works as a fallback when no profile exists —
but expect it to fail on ticket-guarded accounts. Profiles and cookies are
credentials: both folders are gitignored — keep it that way.

### Warm-up ramp (do this before scheduling)
- Week one: post 2-3 videos per account manually in the app, browse a little —
  a fresh account that instantly posts on a robotic schedule is the classic
  shadowban recipe.
- Then: `python main.py --post --account redditregrets --dry-run` (renders and
  shows the caption, uploads nothing).
- Then 2-3 watched live posts: `python main.py --post --account redditregrets`.
- Only then register the schedule:
  `powershell -ExecutionPolicy Bypass -File scripts/register_tasks.ps1`
  (`-Remove` unregisters).
  Note: scheduled runs require the machine on and this user logged in, and a
  Chrome window will briefly open during each upload (the automation drives a
  real browser).

### Day to day
- `python main.py --status` — one glance: per-account login state, queue,
  outbox (with retry counts), last posts.
- History: `posts.jsonl` (one line per attempt).
- Failed uploads park in `outbox/` and **heal themselves**: each scheduled
  `--post` run posts exactly one thing — a queued part 2 first, else the
  oldest parked video (up to `MAX_UPLOAD_RETRIES` = 3 tries, part 1 always
  before its part 2), else a fresh story. After 3 failed retries an entry
  goes manual — `--status` flags it and the `.txt` next to it holds the
  caption for posting by hand.
- Login expired? `--status` shows it; re-run
  `python main.py --login --account <name>` and the backlog drains on the
  following runs.
- **Email alerts**: set the `NOTIFY_*` vars in `.env` (see `.env.example`;
  Gmail wants an app password) and you get a mail on every failed upload,
  when a video exhausts its retries (action needed), and if a scheduled run
  crashes. Unset = silently off. Test it with:
  `python -c "import notify; print(notify.send_failure('test', 'hello'))"`

## Roadmap

- Phase B: TikTok auto-upload + scheduler
- Phase C: GUI (run button, paste-a-URL, freeform text, preview)
- Phase D: virality pack (AI stories, multi-part series, hook overlays)
- Official Reddit API (PRAW) swap-in behind ContentSource, once the API
  application is approved

Design docs: `docs/superpowers/specs/`, plans: `docs/superpowers/plans/`.

