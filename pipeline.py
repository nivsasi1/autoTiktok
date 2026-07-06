"""Story -> TTS -> (split) -> subtitles -> rendered video(s).

The CLI (main.py) and the GUI (gui.py) share this; `log` lets each surface
progress its own way (terminal prints vs. streamed status lines).
"""

import os
import random
from dataclasses import dataclass, field

import config
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


def _part_path(base: str, n: int) -> str:
    root, ext = os.path.splitext(base)
    return f"{root}_part{n}{ext}"


def _render(niche: str, audio_path: str, srt_path: str, out_path: str,
            log=print) -> None:
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
                     ambient=ambient)
    else:
        names = ", ".join(os.path.basename(c) for c, _ in chain)
        log(f"render: {len(chain)}-clip crossfade chain ({names})")
        video.export(chain, audio_path, srt_path, out_path, ambient=ambient)


def render_story(story, preset, niche: str, log=print) -> RenderResult:
    """Render `story` to out.mp4 (and out_part2.mp4 when split)."""
    log(f"tts: {preset.voice}, {len(story.text)} chars")
    boundaries = tts.synthesize(story.text, config.AUDIO_PATH, preset.voice)

    narration = video.get_duration(config.AUDIO_PATH)
    split_plan = None
    if narration > config.SPLIT_THRESHOLD_S:
        split_plan = split.split_boundaries(boundaries, narration)

    result = RenderResult(narration_s=narration)
    if split_plan:
        cut, part1, part2 = split_plan
        log(f"split: {narration:.0f}s narration -> part 1 ({cut:.0f}s) "
            f"+ part 2 ({narration - cut:.0f}s)")
        parts = [(1, part1, 0.0, cut, config.OUTPUT_VID_PATH),
                 (2, part2, cut, None, config.OUTPUT_PART2_PATH)]
        for n, bounds, start, dur, out_path in parts:
            part_audio = _part_path(config.AUDIO_PATH, n)
            part_srt = _part_path(config.SRT_PATH, n)
            video.cut_audio(config.AUDIO_PATH, part_audio, start, dur)
            part_len = cut if n == 1 else narration - cut
            subtitles.write_srt(bounds, part_srt, preset.words_per_line,
                                extra_cues=split.label_cues(n, part_len))
            _render(niche, part_audio, part_srt, out_path, log=log)
            result.videos.append((out_path, n))
    else:
        subtitles.write_srt(boundaries, config.SRT_PATH, preset.words_per_line)
        log(f"subtitles: {config.SRT_PATH} ({preset.words_per_line} words/line)")
        _render(niche, config.AUDIO_PATH, config.SRT_PATH,
                config.OUTPUT_VID_PATH, log=log)
        result.videos.append((config.OUTPUT_VID_PATH, None))
    return result
