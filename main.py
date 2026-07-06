import argparse
import os
import sys

import config
import subtitles
import tts
import video
from sources.askreddit import AskRedditSource
from sources.base import load_used_ids, record_used_id
from sources.reddit_text import RedditTextSource


def build_source(niche: str, preset, used_ids):
    if niche == "askreddit":
        return AskRedditSource(preset, used_ids)
    return RedditTextSource(niche, preset, used_ids)


def main() -> int:
    # redirected stdout defaults to cp1252 on Windows; emoji in story titles
    # would crash prints once a scheduler logs to a file
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Reddit story -> TikTok video")
    parser.add_argument("--niche", choices=sorted(config.NICHES),
                        default=config.DEFAULT_NICHE)
    args = parser.parse_args()
    preset = config.NICHES[args.niche]

    if not os.path.exists(config.INPUT_VID_PATH):
        print(f"error: background clip {config.INPUT_VID_PATH} not found "
              "(see README for a source)")
        return 1

    used_ids = load_used_ids(config.STATE_PATH)
    story = build_source(args.niche, preset, used_ids).fetch()
    if story is None:
        print(f"no qualifying {args.niche} post right now — try again later")
        return 0
    print(f"story: {story.title}\n       {story.url}")

    print(f"tts: {preset.voice}, {len(story.text)} chars")
    boundaries = tts.synthesize(story.text, config.AUDIO_PATH, preset.voice)

    subtitles.write_srt(boundaries, config.SRT_PATH, preset.words_per_line)
    print(f"subtitles: {config.SRT_PATH} ({preset.words_per_line} words/line)")

    offset = video.pick_offset(config.INPUT_VID_PATH, config.AUDIO_PATH)
    print(f"render: background offset {offset:.1f}s")
    video.export(config.INPUT_VID_PATH, config.AUDIO_PATH,
                 config.SRT_PATH, config.OUTPUT_VID_PATH, offset)

    record_used_id(config.STATE_PATH, story.id)
    print(f"done -> {config.OUTPUT_VID_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
