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

## Usage

```
python main.py                      # default niche (drama)
python main.py --niche horror
python main.py --niche askreddit
```

Output: `out.mp4` (1080x1920, captions burned in). Artifacts `output.mp3` /
`subtitles.srt` are left behind for inspection; `state.json` remembers used
posts so you never render the same story twice.

Niche presets (subreddits, voice, words-per-caption, outro) live in
`config.py` — edit them freely.

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
1. Log into the TikTok account in your browser.
2. Export cookies with a "Get cookies.txt LOCALLY"-style extension while on
   tiktok.com; save as `cookies/redditregrets.txt` (resp. `nosleeptonight.txt`).
   Cookies are credentials: the folder is gitignored — keep it that way.

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
- History: `posts.jsonl` (one line per attempt).
- Failed uploads are parked in `outbox/<story_id>.mp4` + `.txt` (the caption) —
  post them by hand, cookies probably need re-exporting.
- A *missing* cookies file gives a clear named error before anything runs.
  *Expired* cookies (file present but stale) surface as an upload failure —
  the video is parked in `outbox/` and you re-export cookies and post it by
  hand.

## Roadmap

- Phase B: TikTok auto-upload + scheduler
- Phase C: GUI (run button, paste-a-URL, freeform text, preview)
- Phase D: virality pack (AI stories, multi-part series, hook overlays)
- Official Reddit API (PRAW) swap-in behind ContentSource, once the API
  application is approved

Design docs: `docs/superpowers/specs/`, plans: `docs/superpowers/plans/`.

