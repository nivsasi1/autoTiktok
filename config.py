import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "autoTiktok/1.0 (public-json)")

# script length bounds (chars of cleaned text; ~750 chars ≈ 1 min of speech)
MIN_CHARS = 500
MAX_CHARS = 2500

# askreddit assembly
ASKREDDIT_MAX_ANSWERS = 8
ASKREDDIT_MIN_SCORE = 100
ASKREDDIT_MAX_ANSWER_CHARS = 350

# artifact paths (repo-root relative; keep SRT_PATH plain — it goes inside an ffmpeg filter)
AUDIO_PATH = "output.mp3"
SRT_PATH = "subtitles.srt"
INPUT_VID_PATH = "vid.mp4"
OUTPUT_VID_PATH = "out.mp4"
STATE_PATH = "state.json"

VIDEO_BITRATE = "2500k"
FORCE_STYLE = (
    "FontName=Arial,Bold=1,Alignment=10,Fontsize=20,"
    "MarginL=20,MarginV=25,Outline=1,OutlineColour=&H80000000"
)

DEFAULT_NICHE = "drama"


@dataclass
class NichePreset:
    subreddits: list[str]
    voice: str
    words_per_line: int
    outro: str


NICHES = {
    "drama": NichePreset(
        subreddits=["AmItheAsshole", "AITAH", "tifu", "TrueOffMyChest",
                    "pettyrevenge", "MaliciousCompliance"],
        voice="en-US-AriaNeural",
        words_per_line=3,
        outro="So, whose side are you on? Comment below.",
    ),
    "horror": NichePreset(
        subreddits=["nosleep", "shortscarystories", "LetsNotMeet"],
        voice="en-US-GuyNeural",
        words_per_line=1,  # word-pop captions
        outro="Follow for more stories like this.",
    ),
    "askreddit": NichePreset(
        subreddits=["AskReddit"],
        voice="en-US-ChristopherNeural",
        words_per_line=2,
        outro="Which one got you? Comment below.",
    ),
}
