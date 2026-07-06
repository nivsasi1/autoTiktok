import html
import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import SimpleNamespace
from xml.etree import ElementTree

import requests

import config
from util import atomic_path

# Lazy URL match with a lookahead: stops before trailing punctuation instead
# of swallowing it, so "https://x.com/a." keeps its sentence-ending period.
_URL = re.compile(r"https?://\S+?(?=[.,;:!?)\]]*(?:\s|$))")
_MD_NOISE = re.compile(r"[*_~^#>|`\[\]]")

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
# the real feed trailer is exactly "submitted by /u/<name> [link] [comments]"
# at the end — requiring the immediate terminals means prose that merely says
# "submitted by /u/xxx" mid-story is never eaten
_TRAILER = re.compile(r"\s*submitted by\s+/u/\S+\s*\[link\]\s*\[comments\]\s*$",
                      re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")

_last_fetch = 0.0  # module-level politeness gap between Reddit hits


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
    text = text.replace("\u200b", " ")
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
    # atomic write: a crash mid-write must not corrupt the state file
    # (load_used_ids would silently reset to empty and re-enable reposts)
    with atomic_path(path) as tmp:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sorted(ids), f)


def fetch_text(url: str) -> str:
    """GET a public Reddit feed; polite spacing + 429-aware backoff."""
    global _last_fetch
    headers = {"User-Agent": config.REDDIT_USER_AGENT}
    status = None
    for attempt in range(3):
        gap = 5.0 - (time.monotonic() - _last_fetch)
        if gap > 0:
            time.sleep(gap)
        _last_fetch = time.monotonic()
        try:
            resp = requests.get(url, headers=headers, timeout=15)
        except requests.RequestException as exc:
            status = f"network error: {exc.__class__.__name__}"
            time.sleep(2 * (attempt + 1))
            continue
        if resp.status_code == 200:
            return resp.text
        status = f"HTTP {resp.status_code}"
        if resp.status_code == 429:            # rate limited: back off hard
            time.sleep(45 * (attempt + 1))
            continue
        if resp.status_code in (500, 502, 503):
            time.sleep(2 * (attempt + 1))
            continue
        break
    raise RuntimeError(
        f"Reddit request failed ({status}) for {url}. Set a descriptive "
        "REDDIT_USER_AGENT in .env (e.g. 'autoTiktok/1.0 by u/<you>') and slow "
        "down if 429 persists.")


def fetch_entries(url: str) -> list[SimpleNamespace]:
    """Fetch an Atom feed and flatten each <entry> to plain attributes."""
    text = fetch_text(url)
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise RuntimeError(
            f"Reddit returned a non-feed response for {url} ({exc}); "
            "likely rate-limited or blocked — try again later.") from exc
    if not root.tag.endswith("feed"):   # e.g. an HTML block/consent page
        raise RuntimeError(
            f"Reddit returned a non-feed response for {url}; "
            "likely rate-limited or blocked — try again later.")
    entries = []
    for e in root.findall("atom:entry", ATOM_NS):
        kind, _, eid = e.findtext("atom:id", "", ATOM_NS).rpartition("_")
        link = e.find("atom:link", ATOM_NS)
        entries.append(SimpleNamespace(
            id=eid,
            kind=kind,          # "t3" post, "t1" comment
            title=e.findtext("atom:title", "", ATOM_NS),
            author=e.findtext("atom:author/atom:name", "", ATOM_NS),
            link=link.get("href") if link is not None else "",
            html=e.findtext("atom:content", "", ATOM_NS) or "",
        ))
    return entries


def html_to_text(fragment: str) -> str:
    """Feed content HTML -> plain text ('submitted by …' trailer removed)."""
    text = _TAG.sub(" ", fragment)
    text = html.unescape(text)
    return _TRAILER.sub("", text)
