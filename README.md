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
3. **(Optional) User-Agent** — no credentials needed; Reddit's public JSON
   endpoints just want a descriptive UA. The default works, but to set your own:
   ```
   copy .env.example .env    # REDDIT_USER_AGENT=autoTiktok/1.0 by u/<you>
   ```
4. **Background clip** — save a gameplay video as `vid.mp4` in the repo root
   (e.g. https://www.youtube.com/watch?v=Pt5_GSKIWQM — 10 min no-copyright
   Minecraft parkour). Longer clip = more variety, since every render starts
   at a random offset.

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

## Roadmap

- Phase B: TikTok auto-upload + scheduler
- Phase C: GUI (run button, paste-a-URL, freeform text, preview)
- Phase D: virality pack (AI stories, multi-part series, hook overlays)
- Official Reddit API (PRAW) swap-in behind ContentSource, once the API
  application is approved

Design docs: `docs/superpowers/specs/`, plans: `docs/superpowers/plans/`.

