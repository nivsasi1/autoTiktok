# autoTiktok — Orange-tier pipeline redesign (Phase A)

Date: 2026-07-05
Status: design approved, pending spec review

## Context

`autoTiktok` turns a Reddit story into a vertical TikTok video: fetch a story →
synthesize speech → burn synced subtitles onto a background (Minecraft) clip.
The original build has three dying/weak subsystems:

- Reddit access via the unauthenticated `.json` endpoint + fake User-Agent (now
  frequently 403'd).
- TTS via `larynx`, which is abandoned.
- Subtitles estimated from word length (`subtitles.py`), which drifts out of
  sync on long posts.

This spec covers **Phase A only**: replacing those three engines and giving the
project a clean, testable module layout. TikTok upload (Phase B) and a GUI
(Phase C) are described in the Roadmap section but are out of scope here.

## Goals

- Reliable Reddit fetching via the official API (PRAW).
- Natural TTS via `edge-tts` (free, tiny dependency, no local model).
- Perfectly synced subtitles built from `edge-tts` word-boundary events — no
  Whisper, no torch.
- A pipeline-aligned module split so each stage is independently testable and so
  Phases B and C are thin additions rather than rewrites.
- Repo hygiene: `requirements.txt`, `.env.example`, `.gitignore`, updated README.

## Non-goals (Phase A)

- TikTok upload (Phase B).
- Any GUI (Phase C).
- Whisper / forced alignment — unnecessary since edge-tts emits boundaries.

## Architecture

Pipeline-aligned modules; `main.py` orchestrates, each stage is a focused unit:

| Module | Responsibility | Key dependency |
|---|---|---|
| `config.py` | Defaults + `.env` loading (subreddit, voice, paths, words-per-line, max chars, bitrate) | python-dotenv |
| `reddit_source.py` | Fetch + filter a story via PRAW; clean the text | praw |
| `tts.py` | `synthesize(text, wav_path) -> list[WordBoundary]` via edge-tts | edge-tts |
| `subtitles.py` | `write_srt(boundaries, srt_path, ...)` — group real timings into caption lines | — (pure) |
| `video.py` | `export(vid, wav, srt, out)` — ffmpeg burn-in (`libx264`) | ffmpeg |
| `main.py` | Orchestrate: fetch → clean → tts → srt → video | above |

### Data flow

```
reddit_source.fetch_story()   -> Story(text, title, author, url)
tts.synthesize(text, wav)     -> writes WAV, returns [WordBoundary(word, start, end)]
subtitles.write_srt(bounds)   -> writes subtitles.srt (caption lines from real timings)
video.export(vid, wav, srt)   -> writes out.mp4 (subs burned in)
```

The subtitle timings come from the same engine that produces the audio, so they
cannot drift.

## Component detail

### config.py
Loads `.env` (via python-dotenv) and exposes typed constants with sensible
defaults. Reddit credentials (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`,
`REDDIT_USER_AGENT`) are referenced by name only — never hardcoded. Other config:
`SUBREDDIT` (default `stories`), `VOICE` (default a good English storytelling
neural voice, e.g. `en-US-AriaNeural`), `WORDS_PER_LINE`, `MAX_CHARS`, file paths,
`VIDEO_BITRATE`.

### reddit_source.py
- `fetch_story(subreddit, ...) -> Story | None`: pull recent/hot posts, apply
  filters, return the first qualifying one (or `None` if none qualify).
- Filters: has non-empty `selftext`, length within `[MIN_CHARS, MAX_CHARS]`,
  not NSFW, not stickied.
- `clean_text(raw) -> str` (separate, pure): strip markdown links/formatting,
  remove URLs, collapse whitespace, truncate at a sentence boundary near
  `MAX_CHARS`. Kept separate so Phase C can reuse it on URL- or textarea-sourced
  content.
- Extension point (documented, not built in Phase A): `fetch_by_url(url)` using
  `reddit.submission(url=...)` for the Phase C "paste a link" mode.

### tts.py
- `synthesize(text, wav_path) -> list[WordBoundary]`: wraps edge-tts's async API
  in `asyncio.run` so callers stay synchronous. Streams audio to `wav_path` and
  collects `WordBoundary` events (word, start, end in seconds).
- Note: edge-tts natively emits MP3; we either request WAV-compatible output or
  transcode once via ffmpeg. Implementation plan will confirm the exact output
  handling and that boundary offsets are converted from 100-ns ticks to seconds.

### subtitles.py (rewrite)
- `write_srt(boundaries, srt_path, words_per_line, max_chars) -> None`: pure
  function grouping consecutive word boundaries into caption lines. A new line
  starts when the line hits `words_per_line`, exceeds `max_chars`, or the current
  word ends a sentence (`.`/`!`/`?`). Each line's start = first word's start,
  end = last word's end. Reuses SRT formatting helpers (with the Phase-1
  hours/minutes fix already in place).
- The old length-based estimation (`calculateWordDuration`, `syllableCount`, the
  `makeSubtitles` heuristic) is deleted.

### video.py
- `export(vid, wav, srt, out) -> None`: the ffmpeg command already corrected in
  the red-tier fixes (`libx264`, `[0:v]...[v]` filter output, `-map [v] -map 1:a`,
  scale `1080:1920`, subtitle burn-in with the existing force_style).

### main.py
Thin orchestrator: `fetch_story → (already cleaned) → synthesize → write_srt →
export`, wrapped in `if __name__ == "__main__":`. Clear, actionable errors when a
prerequisite is missing (`vid.mp4` absent, no qualifying post, network failure).

## Error handling

- Reddit: retry transient failures; if no post qualifies, log and exit cleanly.
- edge-tts: surface network errors with a clear message (it needs internet).
- ffmpeg: fail loudly if `vid.mp4` is missing or ffmpeg isn't installed.
- No silent `except`; log what happened and which stage failed.

## Testing

- **Unit (runnable, no network/ffmpeg):**
  - `subtitles.write_srt`: feed synthetic `WordBoundary` lists → assert exact SRT
    text (grouping, timestamps, sentence breaks).
  - `reddit_source.clean_text`: markdown/URL/whitespace inputs → assert clean
    output and sentence-boundary truncation.
- **Integration (manual or mocked):** PRAW fetch (mock the Reddit client),
  edge-tts synth (live, needs internet), ffmpeg render (live, needs `vid.mp4`).

## Dependencies

`praw`, `edge-tts`, `python-dotenv`. Pinned in `requirements.txt`. Deliberately
no torch / no whisper.

## Repo hygiene

- `requirements.txt` with pinned versions.
- `.env.example` documenting required keys by name (no secrets).
- `.gitignore`: `.env`, `*.wav`, `out.mp4`, `*.srt`, `transcript.*`, venv dirs,
  `__pycache__`.
- README rewritten for PRAW setup, edge-tts, and the new run flow.

## Roadmap (future phases — out of scope here)

- **Phase B — TikTok upload:** an `uploader` module (likely the unofficial
  `tiktok-uploader` via saved cookies, or the official Content Posting API if
  approved). Adds an upload step after `video.export`.
- **Phase C — GUI:** a thin front-end (recommended: Gradio) over the same
  pipeline functions, with three modes: (1) auto-run button, (2) paste Reddit URL
  → preview → upload, (3) freeform text → preview → upload. Preview before
  uploading is a first-class feature. Framework to be confirmed when Phase C is
  specced.
