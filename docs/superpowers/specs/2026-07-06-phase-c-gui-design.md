# autoTiktok — Phase C: Gradio GUI

Date: 2026-07-06
Status: approved (scope locked in the Phase A spec's roadmap; details below)

## Context

The pipeline runs headless (CLI + Task Scheduler). Phase C adds the planned
local GUI: a run button, a paste-Reddit-URL mode, a freeform-text mode, a
preview before upload, and niche/voice pickers. The Phase A spec already chose
Gradio and noted both new input modes are "just more `ContentSource`s".

## Decisions

1. **Gradio Blocks app** in `gui.py`, launched with `python gui.py`, local
   only (`127.0.0.1`, no share link — cookies and drafts stay on the machine).
2. **Pipeline extraction**: the story → TTS → (split) → SRT → render flow
   moves from `main.main()` into `pipeline.py::render_story(story, preset,
   niche) -> RenderResult`. The CLI and the GUI both call it; behavior of
   `main.py` is unchanged (existing flow tests must stay green).
   `RenderResult` carries `[(video_path, part)]`, narration seconds, and the
   split flag — everything the GUI needs for previews and posting.
3. **New sources** (`sources/reddit_url.py`, `sources/freeform.py`):
   - `RedditUrlSource(url, preset, niche)`: appends `.rss` to the post URL
     (`?limit=1`), parses it with the existing `fetch_entries`, cleans with
     `clean_text(MAX_CHARS)`, builds the script with the niche outro. Errors
     (bad URL, deleted post, no selftext) surface as friendly messages.
   - `FreeformSource(title, text, preset, niche)`: cleans the pasted text the
     same way; `id = "freeform-" + sha1(title+text)[:10]` so used-id tracking
     stays consistent.
   - Both niches are user-picked in the GUI; the niche preset supplies voice
     default, caption style, and outro exactly as auto mode does.
4. **GUI layout** (single column, top to bottom):
   - Mode radio: `auto` (niche feed) / `reddit url` / `freeform`, with URL /
     title+text inputs shown per mode.
   - Niche dropdown (drives preset) and voice dropdown (`preset default` +
     the three preset voices; picking one overrides the preset voice).
   - **Render** button → status log streams (story found, tts, split, render)
     → `gr.Video` previews for part 1 (+ part 2 when split) and an editable
     caption per part.
   - **Post** row: account dropdown, dry-run checkbox, Post button. Posting
     part 1 uses the edited caption; a split story queues part 2 with its
     caption via the existing `pending` queue (identical to CLI `--post`).
   - Used-id recording matches the CLI: auto and URL modes record the post id
     after a successful render; freeform never does.
5. **Concurrency**: one render at a time (Gradio default queue); artifact
   paths stay the repo-root singletons (`out.mp4`, …) — same as the CLI, and
   the GUI is a single-user tool.
6. **Dependency**: `gradio` added to `requirements.txt`. Nothing else.

## Error handling

- Source errors (bad URL, story too short, nothing qualifying) and pipeline
  RuntimeErrors (missing clips, ffmpeg) land in the status log, not a
  traceback.
- Post failures reuse `_publish`'s outbox parking; the GUI reports the parked
  path.

## Testing

- Unit: both new sources (mocked feed / pure text), `pipeline.render_story`
  smoke via monkeypatched `tts`/`video`, freeform id stability.
- Existing `test_publish` flow tests guard the `main.py` refactor.
- Live: launch the GUI, render a short freeform story end-to-end via
  `gradio_client`, confirm the preview video exists and plays.

## Non-goals

Editing niche presets from the GUI, a queue/outbox dashboard, remote access,
scheduling from the GUI. The scheduler remains Task Scheduler + CLI.
