import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "autoTiktok/1.0 (rss)")

# script length bounds (chars of cleaned text; ~750 chars ≈ 1 min of speech)
MIN_CHARS = 500
MAX_CHARS = 2500

# askreddit assembly
ASKREDDIT_MAX_ANSWERS = 8
ASKREDDIT_MAX_ANSWER_CHARS = 350

# artifact paths (repo-root relative; keep CAPTIONS_PATH plain — it goes inside an ffmpeg filter)
AUDIO_PATH = "output.mp3"
CAPTIONS_PATH = "captions.ass"
INPUT_VID_PATH = "vid.mp4"          # single-clip fallback
BACKGROUNDS_DIR = "assets/backgrounds"   # theme subfolders of clips (horror/, ...)
CROSSFADE_S = 0.3                   # crossfade between chained background clips
CHAIN_BUFFER_S = 1.0                # chain must outlast the narration by this
OUTPUT_VID_PATH = "out.mp4"
STATE_PATH = "state.json"

# ambient bed: assets/ambient/<niche>/ tracks looped under the narration
AMBIENT_DIR = "assets/ambient"
AMBIENT_VOLUME = 0.12               # quiet enough to feel, not to fight the voice

# long stories become Part 1/2 + 2/2, cut at a mid-story sentence end
SPLIT_THRESHOLD_S = 100
OUTPUT_PART2_PATH = "out_part2.mp4"
QUEUE_DIR = "queue"                 # part 2 waits here for the next --post run

# reddit-style hook card over the opening seconds
HOOK_CARD_S = 3.0
HOOK_CARD_PATH = "hook_card.png"

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

# --- Phase B: posting ---
@dataclass
class Account:
    niche: str             # key into NICHES
    cookies_file: str      # cookies/<name>.txt, exported by the user
    posts_per_day: int     # informational; the schedule lives in Task Scheduler


ACCOUNTS = {
    "redditregrets":  Account("drama",  "cookies/redditregrets.txt",  2),
    "nosleeptonight": Account("horror", "cookies/nosleeptonight.txt", 2),
}

HASHTAGS = {
    "drama": {
        "fixed": ["#redditstories", "#aita", "#storytime"],
        "pool": ["#reddit", "#redditreadings", "#askreddit", "#drama",
                 "#storytimes", "#redditstorytime"],
    },
    "horror": {
        "fixed": ["#scarystories", "#horrortok", "#nosleep"],
        "pool": ["#creepy", "#horror", "#scary", "#creepypasta",
                 "#truescarystories", "#paranormal"],
    },
    "askreddit": {
        "fixed": ["#askreddit", "#redditstories", "#storytime"],
        "pool": ["#reddit", "#redditreadings", "#questions", "#top10",
                 "#redditstorytime", "#fyp"],
    },
}

CAPTION_TITLE_CHARS = 90
POST_JITTER_MAX_S = 900        # extra 0-15 min of human-irregular delay
OUTBOX_DIR = "outbox"
MAX_UPLOAD_RETRIES = 3         # later runs auto-retry parked videos this often
POST_LOG_PATH = "posts.jsonl"
PROFILES_DIR = "profiles"      # persistent browser profiles (credentials!)
