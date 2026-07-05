# autoTiktok — Orange-tier pipeline redesign (Phase A)

Date: 2026-07-05 (rev 4, 2026-07-06)
Status: approved — rev 4: Reddit access via public RSS/Atom feeds. Rev 3's
public-JSON endpoints proved fingerprint-blocked (HTTP 403 for all script
clients regardless of User-Agent, verified empirically); RSS feeds remain open
(HTTP 200, full selftext) since they serve feed readers by design. PRAW/official
API stays the roadmap upgrade behind the ContentSource interface.

## Context

`autoTiktok` turns a story into a vertical TikTok video: fetch content →
synthesize speech → burn synced subtitles onto a background (Minecraft) clip.
The original build has three dying/weak subsystems:

- Reddit access via the unauthenticated `.json` endpoint + fake User-Agent (now
  frequently 403'd).
- TTS via `larynx`, which is abandoned.
- Subtitles estimated from word length, which drift out of sync on long posts.

This spec covers **Phase A**: replacing those engines, introducing a pluggable
content-source architecture with three launch sources (Drama, Horror, AskReddit),
and a clean module layout. Upload (B), GUI (C), and the virality pack (D) are
roadmapped at the end.

## Goals

- Reliable Reddit fetching via the public RSS/Atom feeds (`.../hot.rss`,
  `{permalink}.rss`) with a descriptive User-Agent, polite spacing, and
  429-aware backoff — no credentials required. Known feed limitations accepted:
  no score/over_18/stickied fields (mitigated by feed order ≈ ranking,
  AutoModerator filtering, and title-tag checks).
  (Official-API/PRAW is a later drop-in swap behind ContentSource.)
- Natural TTS via `edge-tts` (free, tiny dependency, no local model).
- Perfectly synced subtitles from `edge-tts` word-boundary events — no torch.
- **Pluggable sources**: one `ContentSource` interface; every future source
  (AI stories, paste-URL, textarea) is just another implementation.
- **Niche presets**: a niche bundles subreddits + voice + caption style + outro,
  so one install can run a drama channel and a horror channel.
- Virality basics that are nearly free: word-pop caption option, random
  background start offset, engagement-bait outro, no-repost tracking.
- Repo hygiene: `requirements.txt`, `.env.example`, `.gitignore`, README rewrite.

## Non-goals (Phase A)

- TikTok upload (Phase B). GUI (Phase C). AI story generation, multi-part series
  splitting, hook title overlay, karaoke ASS captions (Phase D).

## Architecture

```
autoTiktok/
  config.py            # defaults + .env loading + niche presets
  sources/
    base.py            # Story dataclass + ContentSource interface
    reddit_text.py     # selftext posts (Drama & Horror niches)
    askreddit.py       # question + top comments -> list-style script
  tts.py               # synthesize(text, wav) -> [WordBoundary]
  subtitles.py         # write_srt(boundaries, ...) — pure grouping
  video.py             # ffmpeg burn-in (libx264), random bg offset
  main.py              # CLI orchestrator: --niche drama|horror|askreddit
  state.json           # used post IDs (gitignored)
```

### Data flow

```
source.fetch()                -> Story(id, title, text, url, niche)
tts.synthesize(script, wav)   -> writes WAV, returns [WordBoundary(word, start, end)]
subtitles.write_srt(bounds)   -> subtitles.srt (grouped or word-pop)
video.export(vid, wav, srt)   -> out.mp4 (subs burned in, random bg offset)
```

Subtitle timings come from the same engine that speaks — zero drift.

## Component detail

### sources/base.py
- `Story` dataclass: `id, title, text, url, niche`.
- `ContentSource` interface: `fetch() -> Story | None`. Implementations handle
  their own filtering and call the shared cleaner.
- Shared `clean_text(raw) -> str` (pure): strip markdown/URLs, collapse
  whitespace, truncate at a sentence boundary near `MAX_CHARS`.
- Shared used-ID tracking: sources skip IDs recorded in `state.json`; `main`
  records the ID after a successful render. Prevents re-making the same video.

### sources/reddit_text.py
- RSS-backed: `https://www.reddit.com/r/{sub1+sub2}/hot.rss?limit=50` via shared
  `fetch_entries` (UA header, polite spacing, 429 backoff, clear errors); entry
  HTML converted by `html_to_text` (tag strip + "submitted by …" trailer removal)
  then `clean_text`. Filters: non-empty body, length in `[MIN_CHARS, MAX_CHARS]`,
  author not AutoModerator, no NSFW title tag, not already used.
- Script assembly: title + cleaned selftext + niche outro
  (e.g. drama: "So — whose side are you on? Comment below.").

### sources/askreddit.py
- Fetches a hot r/AskReddit question (listing feed), then its comments feed via
  `{permalink}.rss` — first N usable entries in feed order (≈ best ranking; RSS
  exposes no scores), AutoModerator/deleted filtered, cleaned, each capped in
  length.
- Script assembly: question first, then answers with a spoken beat between them
  ("Number 3." or a pause via punctuation) up to `MAX_CHARS`.

### Niche presets (config.py)
| Niche | Subreddits | Voice | Captions | Outro |
|---|---|---|---|---|
| drama | AmItheAsshole, AITAH, tifu, TrueOffMyChest, pettyrevenge, MaliciousCompliance | en-US-AriaNeural | 3 words/line | "Whose side are you on?" |
| horror | nosleep, shortscarystories, LetsNotMeet | en-US-GuyNeural (deeper) | 1 word/line (pop) | "Follow for more." |
| askreddit | AskReddit | en-US-ChristopherNeural | 2 words/line | "Which one got you? Comment below." |

Voices are config defaults, trivially changeable; presets are data, not code.

### tts.py
- `synthesize(text, wav_path) -> list[WordBoundary]`: wraps edge-tts's async API
  in `asyncio.run`. Collects word-boundary events (offsets arrive in 100-ns
  ticks → convert to seconds). edge-tts emits MP3/opus natively; save as-is and
  let ffmpeg consume it, or transcode to WAV — implementation plan confirms the
  simplest reliable path.

### subtitles.py (rewrite)
- `write_srt(boundaries, srt_path, words_per_line, max_chars)`: pure function
  grouping consecutive boundaries into caption lines. New line on:
  words_per_line reached, max_chars exceeded, or sentence end (./!/?).
  `words_per_line=1` gives TikTok-style word-pop captions.
- Line start = first word start; line end = last word end.
- Old heuristic (`calculateWordDuration`, `syllableCount`, `makeSubtitles`)
  is deleted.

### video.py
- `export(vid, audio, srt, out, bg_offset)`: the corrected ffmpeg command
  (`libx264`, `[0:v]...[v]`, `-map [v] -map 1:a`, scale `1080:1920`, burn-in).
- `bg_offset`: random start point into the background clip (`-ss` before `-i`),
  bounded so `clip_length - offset >= audio_length`. Varies visuals between
  videos and avoids duplicate-content detection.

### main.py
- CLI: `python main.py --niche drama` (default niche from config).
- Orchestrates fetch → synthesize → write_srt → export → record used ID.
- Clear errors per stage (missing vid.mp4, no qualifying post, no network,
  ffmpeg missing). No silent excepts. `if __name__ == "__main__":` guard.

## Error handling

- Reddit: retry transient failures; if nothing qualifies, say so and exit 0.
- edge-tts: needs internet — surface a clear message on failure.
- ffmpeg: check invocation return code; fail loudly with the stage named.

## Testing

- **Unit (no network/ffmpeg):** `write_srt` with synthetic boundaries → exact
  SRT assertions (grouping modes, sentence breaks, word-pop). `clean_text`
  markdown/URL/truncation cases. AskReddit script assembly from fake comments.
  Used-ID skip logic with a temp state file.
- **Integration (live, manual):** PRAW fetch per niche, edge-tts synth,
  ffmpeg render with vid.mp4.

## Dependencies

`requests`, `edge-tts`, `python-dotenv` — pinned in `requirements.txt`. No torch,
no praw (until the API application is approved).

## Repo hygiene

`requirements.txt`; `.env.example` (REDDIT_USER_AGENT only — descriptive UA per
Reddit etiquette, e.g. `autoTiktok/1.0 by u/<you>`; no credentials needed);
`.gitignore` (.env, *.wav, *.mp3, out.mp4, *.srt, state.json, venv,
__pycache__); README rewrite (install, per-niche usage, PRAW upgrade note).

## Roadmap

- **Phase B — Auto-posting:** TikTok upload module (unofficial uploader via
  cookies, or official Content Posting API), AI/template titles + hashtags,
  scheduler loop, richer posting-state tracking.
- **Phase C — GUI (Gradio):** run button, paste-Reddit-URL mode, freeform-text
  mode (both are just more `ContentSource`s), preview before upload, niche/voice
  pickers.
- **Phase D — Virality pack:** AI story source (Claude API), multi-part series
  splitter with cliffhanger cuts, hook title overlay (first 2s), karaoke-style
  ASS captions, background clip library rotation.
