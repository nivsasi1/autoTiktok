import html
import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import SimpleNamespace

import requests

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


def get_json(url: str):
    """GET a public Reddit JSON endpoint; retries transient failures."""
    headers = {"User-Agent": config.REDDIT_USER_AGENT}
    status = None
    for attempt in range(3):
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        status = resp.status_code
        if status in (429, 500, 502, 503):
            time.sleep(2 * (attempt + 1))
            continue
        break
    raise RuntimeError(
        f"Reddit request failed (HTTP {status}) for {url}. Set a descriptive "
        "REDDIT_USER_AGENT in .env (e.g. 'autoTiktok/1.0 by u/<you>') and slow "
        "down if it persists.")


def to_obj(d: dict) -> SimpleNamespace:
    return SimpleNamespace(**d)
