# autoTiktok — Background variety (+ account rename, finding-#1 fix)

Date: 2026-07-06 (rev 2: themed folders + crossfaded clip chains)
Status: approved

## Rev 2 — themes + chains (user-directed)

Supersedes the single-random-clip design below:

- **Theme folders**: a subfolder of `assets/backgrounds/` named after a niche is
  reserved for it (`horror/` → horror niche). Niches without a matching folder
  draw a random folder from the unreserved pool (`abstract/`, `food/`,
  `scenic/`) — so horror videos always get horror backgrounds and non-horror
  never does. Folder names are the config.
- **Clip chains**: user clips are short, so `plan_background(niche, needed)`
  shuffles the chosen theme folder and chains whole clips until they cover the
  narration (+1s buffer), staying within one folder per video; clips repeat if
  the folder runs short. If one random clip alone covers the narration it is
  used solo with the classic random start offset.
- **Crossfades**: chained joins use 0.3s xfade (CROSSFADE_S), each join costing
  0.3s of coverage in the planning math. Each clip is normalized
  (1080x1920 center-crop, 30fps, yuv420p) before the joins, so mixed-resolution
  /fps downloads chain cleanly in ONE ffmpeg pass (`build_chain_cmd`).
- **Split interplay**: `needed` is per-rendered-video. When the >100s
  two-part splitter lands, each part plans its own ~50-80s chain — fewer
  repeats per part, as intended.
- Guards: clips ≤ 2×CROSSFADE_S rejected with a clear error (would stall the
  planner); empty theme folder widens to any clip, then `vid.mp4`, then error.
- `pick_offset` absorbed into `main` (single-clip offset math inlined);
  live-verified: 3 mismatched synthetic clips (360p@24/720p@30/portrait@25) →
  1080x1920@30 output, exact narration length.

## Context

TikTok's originality filter flagged the first rendered video as "unoriginal /
low quality." The single biggest trigger for this format is the reused
background clip (the ubiquitous Minecraft parkour is heavily fingerprinted).
This spec adds background rotation so each render uses a different, less-
fingerprinted clip at a random offset — the highest-leverage change against the
flag. It also bundles two small related fixes since they touch the same files:
renaming the config accounts to the user's real TikTok handles, and closing
review finding #1 (an uncaught cookies-constructor crash in `_publish`).

The multi-part splitter (already designed) is a separate follow-on spec.

## Decisions (locked with user)

1. **Background rotation** from `assets/backgrounds/` (the user has created this
   folder and will drop clips in). Falls back to `vid.mp4` if the folder is
   empty/missing. Each render picks a random clip; the existing random start
   offset stays, so clip × offset = double the variety.
2. **Account rename** to real handles: `redditregrets` (drama niche),
   `nosleeptonight` (horror niche). Cookies become
   `cookies/redditregrets.txt` / `cookies/nosleeptonight.txt`; the scheduler
   script updates to match.
3. **Finding #1 fix**: wrap the `CookieUploader(...)` construction (and the
   upload call) in `_publish` so a missing/locked cookies file at post time
   returns a failure that parks the rendered video in the outbox instead of
   crashing uncaught and stranding it.

## Architecture

Small, surgical — no new pipeline stage, one new helper.

### backgrounds
- `config.py`: `BACKGROUNDS_DIR = "assets/backgrounds"`. Keep
  `INPUT_VID_PATH = "vid.mp4"` as the single-clip fallback.
- `video.py`: `pick_background(backgrounds_dir=config.BACKGROUNDS_DIR,
  fallback=config.INPUT_VID_PATH, rng=None) -> str`:
  - list `*.mp4` in `backgrounds_dir` (sorted for determinism); if non-empty,
    return `rng.choice(...)` (rng defaults to the `random` module — injectable
    for tests).
  - else if `fallback` exists, return it.
  - else raise `RuntimeError` naming both the folder and the fallback and how to
    fix (drop clips in `assets/backgrounds/` or add `vid.mp4`).
- `main.py`: replace the two hardcoded `config.INPUT_VID_PATH` uses (the
  existence check + the render) with one `bg = video.pick_background()` call;
  the missing-clip error message points at `assets/backgrounds/`. `pick_offset`
  and `export` receive `bg`.

### account rename (config.py + scripts/register_tasks.ps1)
- `ACCOUNTS = {"redditregrets": Account("drama", "cookies/redditregrets.txt", 2),
  "nosleeptonight": Account("horror", "cookies/nosleeptonight.txt", 2)}`.
- `scripts/register_tasks.ps1`: the `$tasks` list uses `redditregrets` /
  `nosleeptonight` (2 staggered triggers each), everything else unchanged.

### finding #1 fix (main.py `_publish`)
- Wrap the live path's `CookieUploader(...)` construction + `upload()` in
  `try/except Exception`; on failure, build a `PostResult`-shaped failure
  (`ok=False`, `detail=f"{exc.__class__.__name__}: {exc}"`), log it, and park the
  rendered video in the outbox — the same recovery path a normal upload failure
  takes. A missing cookies file (constructor `RuntimeError`) therefore parks the
  video for manual posting instead of crashing after render.

### hygiene
- `.gitignore` += `assets/backgrounds/` (large clips; current ignore only covers
  `out.mp4`/`vid.mp4`). Profile-picture PNGs in `assets/` are left to the user's
  discretion (small brand assets — not ignored by this change).
- README: replace the single-`vid.mp4` instruction with an `assets/backgrounds/`
  section, including sourcing guidance: several varied, **watermark-free** clips;
  avoid the most-fingerprinted ones (Minecraft parkour, Subway Surfers, GTA);
  less-common or self-recorded footage + long clips help most.

## Data flow (unchanged except clip selection)

```
main: bg = video.pick_background()        # random clip, or vid.mp4 fallback
      story = fetch...; tts; write_srt
      offset = video.pick_offset(bg, audio)
      video.export(bg, audio, srt, out, offset)
      (--post) _publish(...)              # now crash-safe on missing cookies
```

## Error handling

- No background at all (empty folder + no vid.mp4): clear `RuntimeError` from
  `pick_background`, surfaced by `main` as a friendly message + exit 1 (mirrors
  today's missing-vid behavior).
- Missing/locked cookies at post time: finding-#1 fix → outbox park, logged, no
  crash.

## Testing

- Unit (no ffmpeg/network):
  - `pick_background`: random pick from a temp dir of fake `.mp4`s (seeded rng →
    deterministic); fallback to `vid.mp4` when the dir is empty; `RuntimeError`
    when neither exists.
  - `_publish` with a fake `CookieUploader` monkeypatched to raise at
    construction → asserts the video is parked in outbox + logged `ok=False` +
    return 1 (no exception) — the finding-#1 regression test.
  - config: every account niche still in `NICHES` (existing test covers renamed
    accounts automatically).
- Integration: a live dry-run after dropping ≥2 clips in `assets/backgrounds/` —
  confirm different runs pick different clips.

## Dependencies

None new (stdlib `random`, `os`).

## Deferred

Multi-part splitter (separate spec, already designed): Part 1/Part 2 split at a
sentence boundary >100s, pending queue posting Part 2 next run, on-screen
PART 1/2 + TO BE CONTINUED text, caption part-labels. AI-rewritten stories and
voice rotation remain later virality items.
