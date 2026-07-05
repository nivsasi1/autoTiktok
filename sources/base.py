import html
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

import praw

import config

# Lazy URL match with a lookahead: stops before trailing punctuation instead
# of swallowing it, so "https://x.com/a." keeps its sentence-ending period.
_URL = re.compile(r"https?://\S+?(?=[.,;:!?)\]]*(?:\s|$))")
_MD_NOISE = re.compile(r"[*_~^#>|`\[\]]")


@dataclass
class Story:
    id: str
    title: str
    text: str   # assembled script, ready for TTS
    url: str
    niche: str


class ContentSource(ABC):
    @abstractmethod
    def fetch(self) -> Story | None:
        """Return the next qualifying story, or None if nothing qualifies."""


def clean_text(raw: str, max_chars: int) -> str:
    # Unescape first so downstream steps see plain chars (handles &#39;, &gt;,
    # &amp; etc.); the zero-width space doesn't match \s so replace it too.
    text = html.unescape(raw)
    text = text.replace("​", " ")
    # Drop markdown link URLs but keep the (possibly nested-bracket) label
    # text, e.g. "[my [nested] post](url)" -> "[my [nested] post]". The
    # leftover brackets get stripped by the noise class below — this sidesteps
    # matching nested brackets with regex entirely.
    text = re.sub(r"\]\([^)]*\)", "]", text)
    text = _URL.sub("", text)
    text = text.replace(" & ", " and ")
    text = _MD_NOISE.sub("", text)
    text = re.sub(r"\(\s*\)", "", text)  # leftover empty parens from a stripped URL
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)  # "out ." -> "out."
    text = re.sub(r"([.,;:!?])[.,;:!?]+", r"\1", text)  # ".," runs -> "."
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        cut = text[:max_chars]
        dot = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
        # only take the sentence cut if it keeps a decent chunk
        if dot > max_chars // 2:
            text = cut[: dot + 1]
        else:
            idx = cut.rfind(" ")
            text = cut[:idx] if idx > 0 else cut  # no space found: keep full cut
    return text.strip()


def load_used_ids(path: str) -> set[str]:
    try:
        with open(path, encoding="utf-8") as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def record_used_id(path: str, story_id: str) -> None:
    ids = load_used_ids(path)
    ids.add(story_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f)


def make_reddit() -> praw.Reddit:
    if not config.REDDIT_CLIENT_ID or not config.REDDIT_CLIENT_SECRET:
        raise RuntimeError(
            "Missing REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET. "
            "Copy .env.example to .env and fill them in "
            "(create a 'script' app at https://www.reddit.com/prefs/apps)."
        )
    return praw.Reddit(
        client_id=config.REDDIT_CLIENT_ID,
        client_secret=config.REDDIT_CLIENT_SECRET,
        user_agent=config.REDDIT_USER_AGENT,
    )
