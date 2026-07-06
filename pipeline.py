"""Story -> TTS -> (split) -> subtitles -> rendered video(s).

The CLI (main.py) and the GUI (gui.py) share this; `log` lets each surface
progress its own way (terminal prints vs. streamed status lines).
"""

import os
import random
from dataclasses import dataclass, field

import config
import hookcard
import split
import subtitles
import tts
import video


@dataclass
class RenderResult:
    # [(video_path, part_number)] — part_number is None for an unsplit video
    videos: list = field(default_factory=list)
    narration_s: float = 0.0

    @property
    def split(self) -> bool:
        return len(self.videos) > 1


def _part_path(base: str, n) -> str:
    root, ext = os.path.splitext(base)
    return f"{root}_part{n}{ext}"


def _short_title(title: str, limit=60) -> str:
    title = " ".join(title.split())
    if len(title) <= limit:
        return title
    cut = title[:limit]
    idx = cut.rfind(" ")
    return (cut[:idx] if idx > 0 else cut).rstrip()


def _make_card(story, niche: str, log) -> str | None:
    """Reddit-style card PNG for the opening; None -> text hook fallback."""
    handle = next((a for a, acc in config.ACCOUNTS.items()
                   if acc.niche == niche), niche)
    avatar = os.path.join("assets", f"pfp_{handle}.png")
    try:
        card = hookcard.make_card(story.title, handle, config.HOOK_CARD_PATH,
                                  avatar_path=avatar)
        log(f"hook: reddit card ({os.path.basename(card)})")
        return card
    except Exception as exc:   # missing fonts/Pillow: hook text still works
        log(f"hook card failed ({exc}); using text hook")
        return None


def _render(niche: str, audio_path: str, srt_path: str, out_path: str,
            card=None, log=print) -> None:
    """Plan a background for this narration and export one video."""
    narration = video.get_duration(audio_path)
    chain = video.plan_background(niche, narration)
    ambient = video.pick_ambient(niche)
    if ambient:
        log(f"ambient: {os.path.basename(ambient)}")
    if len(chain) == 1:
        clip, dur = chain[0]
        if dur < narration + 1.0:
            log(f"warning: {os.path.basename(clip)} ({dur:.0f}s) barely covers "
                f"the narration ({narration:.0f}s); video may cut early")
        offset = random.uniform(0.0, max(dur - narration - 1.0, 0.0))
        log(f"render: {os.path.basename(clip)} @ offset {offset:.1f}s")
        video.export(clip, audio_path, srt_path, out_path, offset,
                     ambient=ambient, card=card)
    else:
        names = ", ".join(os.path.basename(c) for c, _ in chain)
        log(f"render: {len(chain)}-clip crossfade chain ({names})")
        video.export(chain, audio_path, srt_path, out_path, ambient=ambient,
                     card=card)


def _prepend_intro(story, preset, part2, cut, log):
    """Speak "Part 2 of <title>." ahead of the story tail so part 2 opens
    with context instead of resuming mid-thought. Returns (audio, bounds)."""
    intro_text = f"Part 2 of {_short_title(story.title)}."
    intro_path = _part_path(config.AUDIO_PATH, "2_intro")
    intro_bounds = tts.synthesize(intro_text, intro_path, preset.voice)
    intro_len = video.get_duration(intro_path)
    log(f"part 2 intro: {intro_len:.1f}s spoken lead-in")
    tail_path = _part_path(config.AUDIO_PATH, "2_tail")
    video.cut_audio(config.AUDIO_PATH, tail_path, cut)
    part_audio = _part_path(config.AUDIO_PATH, 2)
    video.concat_audio(intro_path, tail_path, part_audio)
    bounds = intro_bounds + [
        subtitles.WordBoundary(b.word, b.start + intro_len, b.end + intro_len)
        for b in part2]
    return part_audio, bounds


def render_story(story, preset, niche: str, log=print) -> RenderResult:
    """Render `story` to out.mp4 (and out_part2.mp4 when split)."""
    log(f"tts: {preset.voice}, {len(story.text)} chars")
    boundaries = tts.synthesize(story.text, config.AUDIO_PATH, preset.voice)

    narration = video.get_duration(config.AUDIO_PATH)
    split_plan = None
    if narration > config.SPLIT_THRESHOLD_S:
        split_plan = split.split_boundaries(boundaries, narration)

    card = _make_card(story, niche, log)
    result = RenderResult(narration_s=narration)
    if split_plan:
        cut, part1, part2 = split_plan
        log(f"split: {narration:.0f}s narration -> part 1 ({cut:.0f}s) "
            f"+ part 2 ({narration - cut:.0f}s)")

        part1_audio = _part_path(config.AUDIO_PATH, 1)
        video.cut_audio(config.AUDIO_PATH, part1_audio, 0.0, cut)
        part2_audio, part2_bounds = _prepend_intro(story, preset, part2, cut,
                                                   log)
        parts = [(1, part1, part1_audio, cut, config.OUTPUT_VID_PATH),
                 (2, part2_bounds, part2_audio,
                  video.get_duration(part2_audio), config.OUTPUT_PART2_PATH)]
        for n, bounds, part_audio, part_len, out_path in parts:
            part_captions = _part_path(config.CAPTIONS_PATH, n)
            # the hook card sells the story once; part 2 opens with its
            # spoken intro + label instead
            subtitles.write_ass(bounds, part_captions, preset.words_per_line,
                                extra_cues=split.label_cues(n, part_len),
                                hook=(story.title if n == 1 and not card
                                      else None))
            _render(niche, part_audio, part_captions, out_path,
                    card=card if n == 1 else None, log=log)
            result.videos.append((out_path, n))
    else:
        subtitles.write_ass(boundaries, config.CAPTIONS_PATH,
                            preset.words_per_line,
                            hook=None if card else story.title)
        log(f"captions: {config.CAPTIONS_PATH} "
            f"({preset.words_per_line} words/line, karaoke)")
        _render(niche, config.AUDIO_PATH, config.CAPTIONS_PATH,
                config.OUTPUT_VID_PATH, card=card, log=log)
        result.videos.append((config.OUTPUT_VID_PATH, None))
    return result
