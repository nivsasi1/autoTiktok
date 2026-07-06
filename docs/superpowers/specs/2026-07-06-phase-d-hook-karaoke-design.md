# autoTiktok — Phase D (part 1): hook overlay + karaoke captions

Date: 2026-07-06
Status: approved (scope from the Phase A roadmap; user asked for these two
Phase D items together)

## Context

Retention features: TikTok weighs the first ~2s heavily (hook), and the
karaoke word-highlight look is the format's current standard. The remaining
Phase D items (AI story source) are out of scope here.

## Decisions

1. **One caption renderer: ASS.** `subtitles.write_ass()` replaces
   `write_srt()` everywhere (the SRT writer and its tests go away; the
   grouping logic `group_boundaries` is unchanged and shared). ASS gives us
   karaoke timing tags, real styles, and the hook overlay in one file —
   no ffmpeg drawtext, no font-path headaches. `config.SRT_PATH` becomes
   `CAPTIONS_PATH = "captions.ass"` (plain name: it sits inside an ffmpeg
   filter).
2. **Karaoke look**: each caption line is one Dialogue event with `{\kf}`
   per word — unsung text white, sung text sweeps to yellow, timed from the
   real edge-tts word boundaries. Word-pop niches (horror, 1 word/line) get
   the same sweep on their single word; multi-word niches read like CapCut
   karaoke. Grouping rules (words_per_line, max_line_chars, sentence
   breaks) are exactly today's.
3. **Sizing**: the ASS header pins PlayResX/Y to 1080x1920 and the styles
   reproduce today's look (Arial bold, ~7% height ≈ fontsize 130, middle-
   center, semi-transparent black outline). Three styles: `Karaoke` (yellow
   primary / white secondary), `Text` (white — PART labels), `Hook` (white,
   fontsize 150, top-center, MarginV 220).
4. **Hook overlay**: the story title (trimmed at a word boundary to
   `HOOK_MAX_CHARS = 70`), shown 0 -> `HOOK_S = 2.5` with a fade
   (`{\fad(150,400)}`), on unsplit videos and part 1 only — part 2 keeps
   just its PART 2/2 label. Braces in user text are sanitized so nothing
   becomes an accidental ASS override tag.
5. **video.py**: `subtitles=<file>` keeps `force_style` for `.srt` inputs
   but omits it for `.ass` (force_style would stomp the karaoke styles).
   `config.FORCE_STYLE` stays for the srt fallback path.
6. **pipeline.py** passes `hook=story.title` for the single video and part 1;
   PART label cues ride through `extra_cues` as today ({\an8} overrides are
   valid ASS inline).

## Error handling

No new failure modes: write_ass is pure file generation; ffmpeg burns .ass
via the same subtitles filter.

## Testing

- write_ass: header/PlayRes, one event per group, `{\kf}` centisecond
  durations from boundaries, hook event (style, fade, trim, brace
  sanitizing), extra cues included, part-2 renders get no hook.
- video: `.ass` omits force_style, `.srt` keeps it.
- pipeline: hook passed for part 1 / unsplit, not part 2.
- Live: full render; frame-check the hook at ~1s and a mid-line frame
  showing the yellow sweep.

## Non-goals

AI story source (separate spec), editable hook text in the GUI (title is the
hook for now), per-niche karaoke on/off switches.
