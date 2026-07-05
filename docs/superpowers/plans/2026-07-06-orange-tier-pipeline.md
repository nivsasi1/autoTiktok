# Orange-Tier Pipeline Rebuild — Implementation Plan (Phase A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dead Reddit scrape / larynx TTS / heuristic subtitles with PRAW + edge-tts + boundary-timed subtitles, behind a pluggable source architecture with three launch niches (drama, horror, askreddit).

**Architecture:** A five-stage pipeline (`source → tts → subtitles → video`, orchestrated by `main.py`) where each stage is a focused module. Content sources implement one interface (`ContentSource.fetch() -> Story | None`); niche presets (subreddits, voice, caption style, outro) are data in `config.py`. Subtitle timings come from edge-tts word-boundary events, so they cannot drift.

**Tech Stack:** Python 3.14 (3.10+ required), requests (public Reddit JSON), edge-tts, python-dotenv, pytest, ffmpeg/ffprobe (system binaries).

> **Rev 2 (2026-07-06):** Reddit ended self-service API key creation (Nov 2025), so PRAW is out for now. Task 10 retrofits Tasks 1/3 output. PRAW returns later as a drop-in `ContentSource` swap if the API application is approved.
>
> **Rev 3 (2026-07-06):** The public JSON endpoints proved fingerprint-blocked (403 for every script client — curl and Python requests, any User-Agent, www/old/api hosts — verified empirically). Reddit's RSS/Atom feeds return 200 with full selftext, so the fetch layer is `fetch_text` / `fetch_entries` / `html_to_text` over `.../hot.rss` and `{permalink}.rss` (Task 10 Steps 7-10). Feed limitations accepted: no score/over_18/stickied fields → feed order ≈ ranking, AutoModerator + NSFW-title-tag filtering. Tasks 4-5 below are written against the RSS design.

**Spec:** `docs/superpowers/specs/2026-07-05-orange-tier-pipeline-design.md`

## Global Constraints

- New dependencies limited to: `requests`, `edge-tts`, `python-dotenv`, `pytest`. **No torch, no whisper, no praw (for now).**
- No credentials required. `.env` (gitignored) optionally holds `REDDIT_USER_AGENT` — a descriptive UA string per Reddit etiquette; config provides a working default. Never hardcode or commit secrets of any kind.
- All text file writes use `encoding="utf-8"` (Windows default cp1252 crashes on Reddit's curly quotes).
- All artifact paths are relative to the repo root and defined once in `config.py`: `output.mp3`, `subtitles.srt`, `vid.mp4`, `out.mp4`, `state.json`.
- Commands below are for Windows PowerShell (`python`, not `python3`).
- This branch (`feat/orange-tier`) rewrites `main.py` and `subtitles.py` wholesale; the red-tier fixes from PR #1 are superseded by these rewrites (the corrected ffmpeg flags are carried into `video.py`).
- Working directory when running the app or ffmpeg: repo root (the subtitle filter uses the relative `subtitles.srt` path).
- Commit style: short, humanized, imperative (e.g. "add subtitle grouping"), one commit per green test cycle.

## Prerequisites (executor must confirm with the user when reached)

1. **No Reddit credentials needed** (rev 2): public JSON endpoints only require a User-Agent header, which config defaults. Live checks and e2e run without any `.env`.
2. **ffmpeg** (Task 7+): not currently installed. Install via `winget install Gyan.FFmpeg` (new terminal afterwards so PATH refreshes) — ask the user before installing.
3. **`vid.mp4`** (Task 7+): user supplies a background gameplay clip in the repo root (the README links a known no-copyright Minecraft parkour video).

---

### Task 1: Repo hygiene + config module

**Files:**
- Create: `requirements.txt`, `.gitignore`, `.env.example`, `config.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `config.NICHES: dict[str, NichePreset]` where `NichePreset(subreddits: list[str], voice: str, words_per_line: int, outro: str)`; constants `MIN_CHARS=500`, `MAX_CHARS=2500`, `ASKREDDIT_MAX_ANSWERS=8`, `ASKREDDIT_MIN_SCORE=100`, `ASKREDDIT_MAX_ANSWER_CHARS=350`, `AUDIO_PATH="output.mp3"`, `SRT_PATH="subtitles.srt"`, `INPUT_VID_PATH="vid.mp4"`, `OUTPUT_VID_PATH="out.mp4"`, `STATE_PATH="state.json"`, `VIDEO_BITRATE="2500k"`, `FORCE_STYLE` (ASS style string), `DEFAULT_NICHE="drama"`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` (from env). All later tasks import from here.

- [ ] **Step 1: Write `requirements.txt`**

```
praw~=7.8
edge-tts~=7.0
python-dotenv~=1.0
pytest~=8.3
```

- [ ] **Step 2: Write `.gitignore`**

```
.env
*.mp3
*.wav
out.mp4
vid.mp4
*.srt
transcript.*
state.json
__pycache__/
*.pyc
.venv/
venv/
larynx_venv/
.pytest_cache/
```

- [ ] **Step 3: Write `.env.example`** (names only, no values)

```
# Reddit "script" app credentials — create one at https://www.reddit.com/prefs/apps
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
# Any descriptive UA string, e.g. autoTiktok/1.0 by <your-reddit-username>
REDDIT_USER_AGENT=
```

- [ ] **Step 4: Write `config.py`**

```python
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "autoTiktok/1.0")

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
```

- [ ] **Step 5: Install deps and verify config imports**

Run: `pip install -r requirements.txt`
Then: `python -c "import config; print(sorted(config.NICHES)); print(config.DEFAULT_NICHE)"`
Expected: `['askreddit', 'drama', 'horror']` then `drama`

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .gitignore .env.example config.py
git commit -m "add config, niche presets, repo hygiene"
```

---

### Task 2: Rewrite `subtitles.py` — boundaries → SRT

**Files:**
- Rewrite: `subtitles.py` (replaces the whole heuristic file)
- Test: `tests/test_subtitles.py` (create `tests/` — no `__init__.py` needed)

**Interfaces:**
- Consumes: nothing (pure module; deliberately no config import).
- Produces: `WordBoundary(word: str, start: float, end: float)` dataclass (seconds); `group_boundaries(boundaries, words_per_line, max_line_chars=32) -> list[tuple[str, float, float]]`; `format_timestamp(seconds: float) -> str` (SRT `HH:MM:SS,mmm`); `write_srt(boundaries, srt_path, words_per_line, max_line_chars=32) -> None`. Task 6 imports `WordBoundary` from here; Task 8 calls `write_srt`.

- [ ] **Step 1: Write the failing tests** — `tests/test_subtitles.py`

```python
from subtitles import WordBoundary, format_timestamp, group_boundaries, write_srt


def wb(word, start, end):
    return WordBoundary(word=word, start=start, end=end)


def test_format_timestamp_rolls_hours_and_pads():
    assert format_timestamp(0) == "00:00:00,000"
    assert format_timestamp(3903.25) == "01:05:03,250"
    assert format_timestamp(78 * 60) == "01:18:00,000"


def test_groups_by_words_per_line():
    bounds = [wb("one", 0.0, 0.3), wb("two", 0.3, 0.6),
              wb("three", 0.6, 0.9), wb("four", 0.9, 1.2)]
    groups = group_boundaries(bounds, words_per_line=3)
    assert groups == [("one two three", 0.0, 0.9), ("four", 0.9, 1.2)]


def test_word_pop_mode_one_word_per_cue():
    bounds = [wb("hi", 0.0, 0.2), wb("there", 0.2, 0.5)]
    assert group_boundaries(bounds, words_per_line=1) == [
        ("hi", 0.0, 0.2), ("there", 0.2, 0.5)]


def test_sentence_end_breaks_line_early():
    bounds = [wb("Done.", 0.0, 0.4), wb("Next", 0.5, 0.8), wb("bit", 0.8, 1.0)]
    groups = group_boundaries(bounds, words_per_line=3)
    assert groups[0] == ("Done.", 0.0, 0.4)
    assert groups[1] == ("Next bit", 0.5, 1.0)


def test_long_line_breaks_on_max_chars():
    bounds = [wb("supercalifragilistic", 0.0, 1.0), wb("expialidocious", 1.0, 2.0)]
    groups = group_boundaries(bounds, words_per_line=5, max_line_chars=20)
    assert len(groups) == 2


def test_write_srt_produces_valid_blocks(tmp_path):
    out = tmp_path / "s.srt"
    write_srt([wb("hey", 0.0, 0.5), wb("you", 0.5, 1.0)], str(out), words_per_line=1)
    text = out.read_text(encoding="utf-8")
    assert text == ("1\n00:00:00,000 --> 00:00:00,500\nhey\n\n"
                    "2\n00:00:00,500 --> 00:00:01,000\nyou\n\n")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_subtitles.py -v`
Expected: FAIL — `ImportError: cannot import name 'WordBoundary'` (old module has none of these names)

- [ ] **Step 3: Replace `subtitles.py` entirely**

Delete all existing content (`resertFiles`, `analyzeRedditPost`, `makeSubtitles`, `calculateWordDuration`, `syllableCount`, transcript handling) and write:

```python
from dataclasses import dataclass


@dataclass
class WordBoundary:
    """One spoken word with real timings (seconds) from the TTS engine."""
    word: str
    start: float
    end: float


def format_timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def group_boundaries(boundaries, words_per_line, max_line_chars=32):
    """Group word boundaries into caption cues: (text, start, end)."""
    groups, current = [], []

    def flush():
        if current:
            groups.append((" ".join(b.word for b in current),
                           current[0].start, current[-1].end))
            current.clear()

    for b in boundaries:
        line_len = sum(len(w.word) for w in current) + len(current) + len(b.word)
        if current and (len(current) >= words_per_line or line_len > max_line_chars):
            flush()
        current.append(b)
        if b.word and b.word[-1] in ".!?":  # end cue at sentence end
            flush()
    flush()
    return groups


def write_srt(boundaries, srt_path, words_per_line, max_line_chars=32):
    groups = group_boundaries(boundaries, words_per_line, max_line_chars)
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, (text, start, end) in enumerate(groups, 1):
            f.write(f"{i}\n{format_timestamp(start)} --> {format_timestamp(end)}\n{text}\n\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_subtitles.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add subtitles.py tests/test_subtitles.py
git commit -m "rewrite subtitles from real word boundaries"
```

---

### Task 3: `sources/base.py` — Story, cleaner, state, interface

**Files:**
- Create: `sources/__init__.py` (empty), `sources/base.py`
- Test: `tests/test_base.py`

**Interfaces:**
- Consumes: `config.REDDIT_CLIENT_ID`, `config.REDDIT_CLIENT_SECRET`, `config.REDDIT_USER_AGENT`.
- Produces: `Story(id: str, title: str, text: str, url: str, niche: str)` (`text` = fully assembled TTS script); `ContentSource` ABC with `fetch(self) -> Story | None`; `clean_text(raw: str, max_chars: int) -> str`; `load_used_ids(path: str) -> set[str]`; `record_used_id(path: str, story_id: str) -> None`; `make_reddit() -> praw.Reddit` (raises `RuntimeError` naming the missing env vars). Tasks 4, 5, 8 consume these.

- [ ] **Step 1: Write the failing tests** — `tests/test_base.py`

```python
import json

from sources.base import clean_text, load_used_ids, record_used_id


def test_clean_strips_markdown_links_and_urls():
    raw = "See [my post](https://x.com/a) and https://y.com/b now"
    assert clean_text(raw, 500) == "See my post and now"


def test_clean_strips_markdown_noise_and_entities():
    raw = "**bold** _it_ &amp; stuff &#x200B; here"
    assert clean_text(raw, 500) == "bold it and stuff here"


def test_clean_collapses_whitespace():
    assert clean_text("a\n\nb\t c", 500) == "a b c"


def test_truncates_at_sentence_boundary():
    raw = "First sentence. Second sentence. Third one that overflows badly."
    out = clean_text(raw, 35)
    assert out == "First sentence. Second sentence."


def test_truncates_at_space_when_no_sentence_end():
    out = clean_text("word " * 30, 32)
    assert len(out) <= 32
    assert not out.endswith(" ")


def test_state_roundtrip(tmp_path):
    p = str(tmp_path / "state.json")
    assert load_used_ids(p) == set()          # missing file -> empty
    record_used_id(p, "abc")
    record_used_id(p, "def")
    assert load_used_ids(p) == {"abc", "def"}
    data = json.loads(open(p, encoding="utf-8").read())
    assert sorted(data) == ["abc", "def"]     # stored as a JSON list


def test_state_survives_corrupt_file(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("not json", encoding="utf-8")
    assert load_used_ids(str(p)) == set()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sources'`

- [ ] **Step 3: Create `sources/__init__.py` (empty) and `sources/base.py`**

```python
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

import praw

import config

_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")
_MD_NOISE = re.compile(r"[*_~^#>|`]")


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
    text = _MD_LINK.sub(r"\1", raw)
    text = _URL.sub("", text)
    text = text.replace("&amp;", "and").replace("&#x200B;", " ")
    text = _MD_NOISE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        cut = text[:max_chars]
        dot = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
        # only take the sentence cut if it keeps a decent chunk
        text = cut[: dot + 1] if dot > max_chars // 2 else cut[: cut.rfind(" ")]
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_base.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add sources/ tests/test_base.py
git commit -m "add source interface, text cleaner, used-id state"
```

---

### Task 4: `sources/reddit_text.py` — Drama & Horror niches

**Files:**
- Create: `sources/reddit_text.py`
- Test: `tests/test_reddit_text.py`

**Interfaces:**
- Consumes: `Story`, `ContentSource`, `clean_text`, `fetch_entries`, `html_to_text` from `sources.base` (RSS layer lands in Task 10 Steps 7-10, which run before this task); `config.MIN_CHARS`, `config.MAX_CHARS`; `NichePreset` fields `subreddits`, `outro`.
- Produces: `qualifies(entry, used_ids) -> bool` (pure; `entry` needs `.id/.kind/.author/.title`); `build_script(title: str, body: str, outro: str) -> str`; `RedditTextSource(niche: str, preset, used_ids: set[str])` implementing `fetch()`. Task 8 constructs it.

- [ ] **Step 1: Write the failing tests** — `tests/test_reddit_text.py` (fakes, no network)

```python
from types import SimpleNamespace

from sources.reddit_text import build_script, qualifies


def entry(**kw):
    base = dict(id="p1", kind="t3", author="/u/someone",
                title="A normal story", html="<p>story</p>")
    base.update(kw)
    return SimpleNamespace(**base)


def test_qualifies_accepts_normal_post():
    assert qualifies(entry(), used_ids=set())


def test_rejects_used_automod_nsfw_and_non_posts():
    assert not qualifies(entry(), used_ids={"p1"})
    assert not qualifies(entry(author="/u/AutoModerator"), used_ids=set())
    assert not qualifies(entry(title="[NSFW] wild story"), used_ids=set())
    assert not qualifies(entry(kind="t1"), used_ids=set())


def test_build_script_joins_title_body_outro():
    s = build_script("My title", "The story body.", "Comment below.")
    assert s == "My title. The story body. Comment below."


def test_build_script_keeps_title_end_punctuation():
    s = build_script("Am I wrong?", "Body.", "Outro.")
    assert s == "Am I wrong? Body. Outro."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_reddit_text.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sources.reddit_text'`

- [ ] **Step 3: Write `sources/reddit_text.py`**

```python
import config
from sources.base import (ContentSource, Story, clean_text, fetch_entries,
                          html_to_text)

LISTING_URL = "https://www.reddit.com/r/{subs}/hot.rss?limit=50"


def qualifies(entry, used_ids) -> bool:
    # RSS has no over_18/stickied flags: filter AutoModerator + NSFW title tags
    title = (entry.title or "").lower()
    return (entry.kind == "t3"
            and entry.id not in used_ids
            and entry.author.lower() != "/u/automoderator"
            and "nsfw" not in title[:16])


def build_script(title: str, body: str, outro: str) -> str:
    if title and title[-1] not in ".!?":
        title += "."
    return f"{title} {body} {outro}"


class RedditTextSource(ContentSource):
    """Selftext-post source; drama and horror niches differ only by preset."""

    def __init__(self, niche: str, preset, used_ids: set[str]):
        self.niche = niche
        self.preset = preset
        self.used_ids = used_ids

    def fetch(self) -> Story | None:
        url = LISTING_URL.format(subs="+".join(self.preset.subreddits))
        for entry in fetch_entries(url):
            if not qualifies(entry, self.used_ids):
                continue
            body = clean_text(html_to_text(entry.html), config.MAX_CHARS)
            if len(body) < config.MIN_CHARS:
                continue
            title = clean_text(entry.title, 300)
            return Story(
                id=entry.id,
                title=title,
                text=build_script(title, body, self.preset.outro),
                url=entry.link,
                niche=self.niche,
            )
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_reddit_text.py -v`
Expected: 4 passed

- [ ] **Step 5: Live check (needs internet only — no credentials)**

Run: `python -c "import config; from sources.base import load_used_ids; from sources.reddit_text import RedditTextSource; s = RedditTextSource('drama', config.NICHES['drama'], load_used_ids(config.STATE_PATH)); st = s.fetch(); print(st.title if st else 'none qualified'); print((st.url, len(st.text)) if st else '')"`
Expected: a real post title + URL + script length between ~500 and ~2600.

- [ ] **Step 6: Commit**

```bash
git add sources/reddit_text.py tests/test_reddit_text.py
git commit -m "add reddit selftext source for drama and horror"
```

---

### Task 5: `sources/askreddit.py` — question + top comments

**Files:**
- Create: `sources/askreddit.py`
- Test: `tests/test_askreddit.py`

**Interfaces:**
- Consumes: `Story`, `ContentSource`, `clean_text`, `fetch_entries`, `html_to_text` from `sources.base` (RSS layer from Task 10 Steps 7-10); `config.ASKREDDIT_MAX_ANSWERS`, `config.ASKREDDIT_MAX_ANSWER_CHARS`, `config.MAX_CHARS`.
- Produces: `usable_comment(entry) -> bool` (pure; needs `.kind/.author/.html`); `build_script(title: str, answers: list[str], outro: str, max_chars=config.MAX_CHARS) -> str` (numbers the answers, stops before overflowing); `AskRedditSource(preset, used_ids: set[str])` implementing `fetch()` with `niche="askreddit"`. Task 8 constructs it.

- [ ] **Step 1: Write the failing tests** — `tests/test_askreddit.py`

```python
from types import SimpleNamespace

from sources.askreddit import build_script, usable_comment


def centry(**kw):
    base = dict(id="c1", kind="t1", author="/u/replier",
                html="<p>A solid answer here.</p>")
    base.update(kw)
    return SimpleNamespace(**base)


def test_usable_comment_filters():
    assert usable_comment(centry())
    assert not usable_comment(centry(kind="t3"))
    assert not usable_comment(centry(author="/u/AutoModerator"))
    assert not usable_comment(centry(author=""))
    assert not usable_comment(centry(html="   "))


def test_build_script_numbers_answers():
    s = build_script("Weirdest thing seen at night?",
                     ["A fox in a hat.", "Nothing, ever."], "Comment below.")
    assert s == ("Weirdest thing seen at night? Number 1. A fox in a hat. "
                 "Number 2. Nothing, ever. Comment below.")


def test_build_script_adds_question_mark_to_bare_title():
    s = build_script("Weirdest thing seen at night", ["An owl."], "Bye.")
    assert s.startswith("Weirdest thing seen at night? Number 1.")


def test_build_script_stops_before_max_chars():
    answers = [f"Answer number {i} padded out to be long." for i in range(50)]
    s = build_script("Q?", answers, "Out.", max_chars=300)
    assert len(s) <= 300
    assert s.endswith("Out.")
    assert "Number 1." in s and "Number 50." not in s
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_askreddit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sources.askreddit'`

- [ ] **Step 3: Write `sources/askreddit.py`**

```python
import config
from sources.base import (ContentSource, Story, clean_text, fetch_entries,
                          html_to_text)

LISTING_URL = "https://www.reddit.com/r/AskReddit/hot.rss?limit=25"


def usable_comment(entry) -> bool:
    # feed order ≈ best ranking; RSS exposes no scores
    return (entry.kind == "t1"
            and entry.author.lower() not in ("", "/u/automoderator")
            and bool((entry.html or "").strip()))


def build_script(title: str, answers: list[str], outro: str,
                 max_chars=config.MAX_CHARS) -> str:
    if title and title[-1] not in ".!?":
        title += "?"  # AskReddit titles are questions
    script = title
    budget = max_chars - len(outro) - 1
    for i, answer in enumerate(answers, 1):
        piece = f" Number {i}. {answer}"
        if len(script) + len(piece) > budget:
            break
        script += piece
    return f"{script} {outro}"


class AskRedditSource(ContentSource):
    """Question + top comments assembled into a list-style script."""

    def __init__(self, preset, used_ids: set[str]):
        self.preset = preset
        self.used_ids = used_ids

    def fetch(self) -> Story | None:
        for post in fetch_entries(LISTING_URL):
            if (post.kind != "t3" or post.id in self.used_ids
                    or post.author.lower() == "/u/automoderator"):
                continue
            comments = fetch_entries(post.link.rstrip("/") + "/.rss?limit=25")
            answers = []
            for c in comments:  # feed order ≈ best ranking
                if not usable_comment(c):
                    continue
                body = clean_text(html_to_text(c.html),
                                  config.ASKREDDIT_MAX_ANSWER_CHARS)
                if len(body) < 20 or body.lower() in ("deleted", "removed"):
                    continue
                answers.append(body)
                if len(answers) == config.ASKREDDIT_MAX_ANSWERS:
                    break
            if len(answers) < 3:  # not enough for a list video
                continue
            title = clean_text(post.title, 300)
            return Story(
                id=post.id,
                title=title,
                text=build_script(title, answers, self.preset.outro),
                url=post.link,
                niche="askreddit",
            )
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_askreddit.py -v`
Expected: 4 passed

- [ ] **Step 5: Live check (needs internet only — no credentials)**

Run: `python -c "import config; from sources.base import load_used_ids; from sources.askreddit import AskRedditSource; s = AskRedditSource(config.NICHES['askreddit'], load_used_ids(config.STATE_PATH)); st = s.fetch(); print(st.text[:300] if st else 'none qualified')"`
Expected: question + "Number 1." style script excerpt.

- [ ] **Step 6: Commit**

```bash
git add sources/askreddit.py tests/test_askreddit.py
git commit -m "add askreddit question-plus-comments source"
```

---

### Task 6: `tts.py` — edge-tts synthesis with word boundaries

**Files:**
- Create: `tts.py` (new module; the old larynx call lives in `main.py` and dies in Task 8)

**Interfaces:**
- Consumes: `WordBoundary` from `subtitles` (Task 2).
- Produces: `synthesize(text: str, audio_path: str, voice: str) -> list[WordBoundary]` — writes MP3 bytes to `audio_path`, returns boundaries in seconds, sorted, non-empty for non-empty text. Task 8 calls it. **Design note:** edge-tts natively streams MP3; we save it as-is (`output.mp3`) and let ffmpeg consume it directly — no WAV transcode step. Boundary offsets arrive in 100-nanosecond ticks; divide by 10,000,000 for seconds.

- [ ] **Step 1: Write `tts.py`**

```python
import asyncio

import edge_tts

from subtitles import WordBoundary

_TICKS_PER_SECOND = 10_000_000  # edge-tts offsets are 100-ns ticks


async def _synthesize(text: str, audio_path: str, voice: str) -> list[WordBoundary]:
    communicate = edge_tts.Communicate(text, voice)
    boundaries: list[WordBoundary] = []
    with open(audio_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / _TICKS_PER_SECOND
                end = (chunk["offset"] + chunk["duration"]) / _TICKS_PER_SECOND
                boundaries.append(WordBoundary(chunk["text"], start, end))
    return boundaries


def synthesize(text: str, audio_path: str, voice: str) -> list[WordBoundary]:
    """Speak `text` into `audio_path` (mp3); return real word timings."""
    boundaries = asyncio.run(_synthesize(text, audio_path, voice))
    if not boundaries:
        raise RuntimeError("edge-tts returned no word boundaries — is the "
                           "voice name valid and the network up?")
    return boundaries
```

- [ ] **Step 2: Live verification (needs internet, no credentials)**

Run: `python -c "from tts import synthesize; import os; b = synthesize('Hello there. This is a boundary test.', 'test.mp3', 'en-US-AriaNeural'); print(len(b), 'boundaries'); print(b[0], b[-1]); print('mp3 bytes:', os.path.getsize('test.mp3')); assert b[0].start < b[-1].end; os.remove('test.mp3')"`
Expected: ~8 boundaries; first starts near 0.0; mp3 bytes > 10000; no assertion error.

- [ ] **Step 3: Commit**

```bash
git add tts.py
git commit -m "add edge-tts synthesis with word boundaries"
```

---

### Task 7: `video.py` — ffmpeg burn-in with random background offset

**Files:**
- Create: `video.py`
- Test: `tests/test_video.py`

**Interfaces:**
- Consumes: `config.FORCE_STYLE`, `config.VIDEO_BITRATE`.
- Produces: `build_cmd(vid, audio, srt, out, bg_offset, bitrate=config.VIDEO_BITRATE, force_style=config.FORCE_STYLE) -> list[str]` (pure); `get_duration(path: str) -> float` (ffprobe); `pick_offset(vid_path: str, audio_path: str) -> float` (random start, leaves room for the narration; 0.0 + warning if the clip is too short); `export(vid, audio, srt, out, bg_offset) -> None` (raises `RuntimeError` naming ffmpeg on failure). Task 8 calls `pick_offset` then `export`.
- **Prerequisite gate:** before Step 4, ffmpeg must be installed — ask the user, then `winget install Gyan.FFmpeg` and open a fresh terminal. Steps 1–3 need no ffmpeg.

- [ ] **Step 1: Write the failing test** — `tests/test_video.py` (command construction only, no ffmpeg)

```python
from video import build_cmd


def test_build_cmd_maps_filtered_video_and_audio():
    cmd = build_cmd("vid.mp4", "output.mp3", "subtitles.srt", "out.mp4",
                    bg_offset=12.5)
    joined = " ".join(cmd)
    assert cmd[0] == "ffmpeg"
    assert "-ss 12.50" in joined          # seek before the video input
    assert joined.index("-ss") < joined.index("vid.mp4")
    assert "[0:v]" in joined and "[v]" in joined
    assert "-map [v] -map 1:a" in joined  # video from filter, audio from mp3
    assert "libx264" in joined
    assert "subtitles=subtitles.srt" in joined
    assert cmd[-1] == "out.mp4"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_video.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'video'`

- [ ] **Step 3: Write `video.py`**

```python
import random
import subprocess

import config


def build_cmd(vid, audio, srt, out, bg_offset,
              bitrate=config.VIDEO_BITRATE, force_style=config.FORCE_STYLE):
    # center-crop to 9:16 whatever the source resolution, then burn subtitles
    vf = (f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
          f"crop=1080:1920,subtitles={srt}:force_style='{force_style}'[v]")
    return ["ffmpeg", "-y",
            "-ss", f"{bg_offset:.2f}", "-i", vid,   # fast-seek the background
            "-i", audio,
            "-filter_complex", vf,
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-b:v", bitrate,
            "-c:a", "aac",
            "-shortest", out]


def get_duration(path: str) -> float:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {res.stderr.strip()}")
    return float(res.stdout.strip())


def pick_offset(vid_path: str, audio_path: str) -> float:
    """Random start into the background clip, leaving room for the narration."""
    vid_len = get_duration(vid_path)
    audio_len = get_duration(audio_path)
    max_offset = vid_len - audio_len - 1.0
    if max_offset <= 0:
        print(f"warning: {vid_path} ({vid_len:.0f}s) is shorter than the "
              f"narration ({audio_len:.0f}s); video will cut early")
        return 0.0
    return random.uniform(0.0, max_offset)


def export(vid, audio, srt, out, bg_offset) -> None:
    cmd = build_cmd(vid, audio, srt, out, bg_offset)
    res = subprocess.run(cmd)
    if res.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed — is ffmpeg installed and on PATH, and do "
            f"{vid}/{audio}/{srt} all exist? (exit {res.returncode})")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_video.py -v`
Expected: 1 passed

- [ ] **Step 5: Install ffmpeg (ask user first) and verify binaries**

Run: `winget install Gyan.FFmpeg` → new terminal → `ffmpeg -version; ffprobe -version`
Expected: version banners for both.

- [ ] **Step 6: Live render check (needs ffmpeg; generates its own inputs, not `vid.mp4`)**

```powershell
ffmpeg -y -f lavfi -i testsrc=duration=30:size=640x360:rate=30 fake_vid.mp4
python -c "from tts import synthesize; from subtitles import write_srt; b = synthesize('This is a full render test. It should show captions.', 'output.mp3', 'en-US-AriaNeural'); write_srt(b, 'subtitles.srt', words_per_line=2)"
python -c "from video import pick_offset, export; off = pick_offset('fake_vid.mp4', 'output.mp3'); export('fake_vid.mp4', 'output.mp3', 'subtitles.srt', 'out.mp4', off); print('offset', off)"
python -c "from video import get_duration; print('out.mp4 seconds:', get_duration('out.mp4'))"
```
Expected: `out.mp4` exists; duration ≈ narration length (~4s), NOT 30s (proves `-map`/`-shortest` are right). Open `out.mp4` and confirm captions are visible and synced. Then delete scratch: `del fake_vid.mp4 out.mp4 output.mp3 subtitles.srt`.

- [ ] **Step 7: Commit**

```bash
git add video.py tests/test_video.py
git commit -m "add ffmpeg export with random background offset"
```

---

### Task 8: Rewrite `main.py` — CLI orchestrator

**Files:**
- Rewrite: `main.py` (delete: `headers`, `getRedditPost`, `generateAudioFile`, `getAudioLength`, the module-level `main()` call, and the `json`/`requests`/`wave`/`contextlib` imports — `requests` drops out of the dependency set entirely)

**Interfaces:**
- Consumes: everything above — `config.NICHES/DEFAULT_NICHE/paths`, `load_used_ids/record_used_id`, `RedditTextSource`, `AskRedditSource`, `tts.synthesize`, `subtitles.write_srt`, `video.pick_offset/export`.
- Produces: `python main.py [--niche drama|horror|askreddit]` end-to-end run; `build_source(niche: str, preset, used_ids) -> ContentSource` (askreddit → `AskRedditSource`, else `RedditTextSource`).

- [ ] **Step 1: Replace `main.py` entirely**

```python
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
```

- [ ] **Step 2: Full unit suite still green**

Run: `python -m pytest tests/ -v`
Expected: all tests pass (subtitles 6, base 7, reddit_text 4, askreddit 4, video 1 = 22).

- [ ] **Step 3: CLI sanity without prerequisites**

Run: `python main.py --help` → usage text with `--niche {askreddit,drama,horror}`.
Then rename any `vid.mp4` away and run `python main.py` → clean error about the missing background clip, exit code 1 (no traceback).

- [ ] **Step 4: End-to-end run (gate: ffmpeg installed, real `vid.mp4` present — coordinate with the user; no credentials needed)**

Run: `python main.py --niche drama`
Expected: story title + URL printed, `out.mp4` produced; open it — narration audible, captions synced, vertical 1080x1920. Run again: a *different* story (used-ID skip working).
Also run: `python main.py --niche horror` (word-pop captions) and `--niche askreddit` (numbered answers).

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "rewrite main as niche-driven pipeline"
```

---

### Task 9: README rewrite + wrap-up

**Files:**
- Rewrite: `README.md`

- [ ] **Step 1: Replace `README.md`**

```markdown
# autoTiktok

Reddit story → TTS narration → vertical video with perfectly-synced captions,
ready for TikTok. Three built-in niches: **drama** (AITA, revenge, TIFU),
**horror** (nosleep & co., word-pop captions), **askreddit** (question + top
answers).

## Setup

1. **Python deps** (3.10+):
   ```
   pip install -r requirements.txt
   ```
2. **ffmpeg** (includes ffprobe):
   ```
   winget install Gyan.FFmpeg
   ```
   (new terminal afterwards so PATH refreshes)
3. **(Optional) User-Agent** — no credentials needed; Reddit's public JSON
   endpoints just want a descriptive UA. The default works, but to set your own:
   ```
   copy .env.example .env    # REDDIT_USER_AGENT=autoTiktok/1.0 by u/<you>
   ```
4. **Background clip** — save a gameplay video as `vid.mp4` in the repo root
   (e.g. https://www.youtube.com/watch?v=Pt5_GSKIWQM — 10 min no-copyright
   Minecraft parkour). Longer clip = more variety, since every render starts
   at a random offset.

## Usage

```
python main.py                      # default niche (drama)
python main.py --niche horror
python main.py --niche askreddit
```

Output: `out.mp4` (1080x1920, captions burned in). Artifacts `output.mp3` /
`subtitles.srt` are left behind for inspection; `state.json` remembers used
posts so you never render the same story twice.

Niche presets (subreddits, voice, words-per-caption, outro) live in
`config.py` — edit them freely.

## Tests

```
python -m pytest tests/ -v
```

## Roadmap

- Phase B: TikTok auto-upload + scheduler
- Phase C: GUI (run button, paste-a-URL, freeform text, preview)
- Phase D: virality pack (AI stories, multi-part series, hook overlays)
- Official Reddit API (PRAW) swap-in behind ContentSource, once the API
  application is approved

Design docs: `docs/superpowers/specs/`, plans: `docs/superpowers/plans/`.
```

- [ ] **Step 2: Final full check**

Run: `python -m pytest tests/ -v` → all green. `git status` → clean tree except intended files.

- [ ] **Step 3: Commit and push**

```bash
git add README.md
git commit -m "rewrite readme for new pipeline"
git push
```

- [ ] **Step 4: Open PR** — `feat/orange-tier` → `main`, title "Orange tier: pluggable sources, edge-tts, boundary subtitles", body summarizing the three engine swaps + niches, noting it supersedes PR #1's file versions.

---

### Task 10: Public-JSON pivot retrofit (executes between Tasks 3 and 4)

Reddit ended self-service API keys (Nov 2025) — this task retires praw/make_reddit
and gives Tasks 4/5 the `get_json`/`to_obj` helpers they consume.

**Files:**
- Modify: `requirements.txt`, `.env.example`, `config.py`, `sources/base.py`
- Test: `tests/test_base.py` (extend)

**Interfaces:**
- Consumes: `config.REDDIT_USER_AGENT`.
- Produces: `get_json(url: str) -> dict | list` (sends the UA header, 15s timeout,
  3 attempts with backoff on 429/500/502/503, else `RuntimeError` whose message
  names `REDDIT_USER_AGENT`); `to_obj(d: dict) -> SimpleNamespace` (attribute
  access over Reddit JSON dicts, so `qualifies`/`usable_comment` fakes in Tasks
  4/5 keep working). **Removes** `make_reddit` and the praw import entirely.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_base.py` (add `import pytest` if absent)

```python
class FakeResp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_get_json_returns_parsed_payload(monkeypatch):
    from sources import base
    monkeypatch.setattr(base.requests, "get",
                        lambda url, headers, timeout: FakeResp(200, {"ok": 1}))
    assert base.get_json("https://x") == {"ok": 1}


def test_get_json_sends_user_agent(monkeypatch):
    from sources import base
    seen = {}

    def fake_get(url, headers, timeout):
        seen.update(headers)
        return FakeResp(200, [])

    monkeypatch.setattr(base.requests, "get", fake_get)
    base.get_json("https://x")
    assert seen["User-Agent"]


def test_get_json_raises_clear_error_on_403(monkeypatch):
    from sources import base
    monkeypatch.setattr(base.requests, "get",
                        lambda url, headers, timeout: FakeResp(403))
    with pytest.raises(RuntimeError, match="REDDIT_USER_AGENT"):
        base.get_json("https://x")


def test_get_json_retries_429_then_succeeds(monkeypatch):
    from sources import base
    calls = []

    def fake_get(url, headers, timeout):
        calls.append(1)
        return FakeResp(429) if len(calls) == 1 else FakeResp(200, {"ok": 2})

    monkeypatch.setattr(base.requests, "get", fake_get)
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    assert base.get_json("https://x") == {"ok": 2}
    assert len(calls) == 2


def test_to_obj_gives_attribute_access():
    from sources.base import to_obj
    o = to_obj({"id": "x1", "over_18": False, "selftext": "hi"})
    assert o.id == "x1" and o.over_18 is False and o.selftext == "hi"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_base.py -v`
Expected: 5 new tests FAIL (`AttributeError: module 'sources.base' has no attribute 'requests'` / no `get_json`); 13 existing PASS.

- [ ] **Step 3: Implement the pivot**

`requirements.txt`: replace the `praw~=7.8` line with `requests~=2.32`, then `pip install -r requirements.txt`.

`.env.example` — replace entire content:

```
# Optional: descriptive User-Agent for Reddit's public JSON endpoints
# (Reddit etiquette: include your reddit username)
REDDIT_USER_AGENT=autoTiktok/1.0 by u/<your-username>
```

`config.py`: delete the `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` lines; change the UA default to
`REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "autoTiktok/1.0 (public-json)")`.

`sources/base.py`: delete `import praw` and the whole `make_reddit` function; add near the top `import time`, `from types import SimpleNamespace`, `import requests`; add:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: 24 passed (6 subtitles + 18 base), zero praw imports remaining (`grep -r praw *.py sources/` finds nothing).

- [ ] **Step 5: Live check (internet only, no credentials)**

Run: `python -c "from sources.base import get_json; d = get_json('https://www.reddit.com/r/stories/hot.json?limit=5&raw_json=1'); print(len(d['data']['children']), 'posts fetched')"`
Expected: `5 posts fetched` (or fewer if the sub is quiet).

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .env.example config.py sources/base.py tests/test_base.py
git commit -m "switch reddit access to public json endpoints"
```

#### RSS extension (Steps 7-10, rev 3) — JSON endpoints are fingerprint-blocked; feeds are the working path

Replaces `get_json`/`to_obj` (and their 5 tests) with an Atom-feed fetch layer.
`config.ASKREDDIT_MIN_SCORE` is deleted too (RSS has no scores).

**Produces (final Task 10 interface):** `fetch_text(url) -> str` (UA header, ≥5s
politeness gap between calls, 3 attempts, 45s/90s backoff on 429, 2s/4s on
500/502/503, else RuntimeError naming REDDIT_USER_AGENT); `fetch_entries(url)
-> list[SimpleNamespace]` with fields `id` (prefix-stripped), `kind` ("t3"
post / "t1" comment), `title`, `author` (like "/u/name"), `link`, `html`;
`html_to_text(fragment) -> str` (tags stripped, entities unescaped, trailing
"submitted by /u/…" trailer removed).

- [ ] **Step 7: Write the failing tests** — in `tests/test_base.py`, DELETE the five `get_json`/`to_obj` tests and add:

```python
FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <author><name>/u/writer</name></author>
    <id>t3_abc12</id>
    <link href="https://www.reddit.com/r/stories/comments/abc12/tale/"/>
    <title>A tale</title>
    <content type="html">&lt;div class="md"&gt;&lt;p&gt;Hello story.&lt;/p&gt;&lt;/div&gt; submitted by &lt;a&gt;/u/writer&lt;/a&gt; [link] [comments]</content>
  </entry>
  <entry>
    <author><name>/u/replier</name></author>
    <id>t1_xyz99</id>
    <link href="https://www.reddit.com/r/stories/comments/abc12/tale/xyz99/"/>
    <title>replier on A tale</title>
    <content type="html">&lt;p&gt;Nice one.&lt;/p&gt;</content>
  </entry>
</feed>"""


class FakeResp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


def test_fetch_text_sends_user_agent(monkeypatch):
    from sources import base
    seen = {}

    def fake_get(url, headers, timeout):
        seen.update(headers)
        return FakeResp(200, "ok")

    monkeypatch.setattr(base.requests, "get", fake_get)
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    assert base.fetch_text("https://x") == "ok"
    assert seen["User-Agent"]


def test_fetch_text_raises_clear_error_on_403(monkeypatch):
    from sources import base
    monkeypatch.setattr(base.requests, "get",
                        lambda url, headers, timeout: FakeResp(403))
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="REDDIT_USER_AGENT"):
        base.fetch_text("https://x")


def test_fetch_text_retries_429_then_succeeds(monkeypatch):
    from sources import base
    calls = []

    def fake_get(url, headers, timeout):
        calls.append(1)
        return FakeResp(429) if len(calls) == 1 else FakeResp(200, "fine")

    monkeypatch.setattr(base.requests, "get", fake_get)
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    assert base.fetch_text("https://x") == "fine"
    assert len(calls) == 2


def test_fetch_entries_parses_atom(monkeypatch):
    from sources import base
    monkeypatch.setattr(base, "fetch_text", lambda url: FEED)
    posts = base.fetch_entries("https://x")
    assert posts[0].kind == "t3" and posts[0].id == "abc12"
    assert posts[0].author == "/u/writer"
    assert posts[0].title == "A tale"
    assert posts[0].link.endswith("/tale/")
    assert "Hello story." in posts[0].html
    assert posts[1].kind == "t1" and posts[1].id == "xyz99"


def test_html_to_text_strips_tags_and_trailer():
    from sources.base import html_to_text
    frag = ('<div class="md"><p>Hello story.</p></div> submitted by '
            '<a href="u">/u/writer</a> <span>[link]</span> <span>[comments]</span>')
    assert " ".join(html_to_text(frag).split()) == "Hello story."


def test_html_to_text_keeps_prose_mentioning_submitted_by():
    from sources.base import html_to_text
    frag = "<p>I saw a post submitted by /u/foo yesterday. It got worse.</p>"
    out = " ".join(html_to_text(frag).split())
    assert out == "I saw a post submitted by /u/foo yesterday. It got worse."


def test_html_to_text_compound_prose_and_real_trailer():
    from sources.base import html_to_text
    frag = ("<p>I saw a post submitted by /u/foo earlier. The drama grew.</p> "
            "submitted by <a>/u/writer</a> <span>[link]</span> "
            "<span>[comments]</span>")
    out = " ".join(html_to_text(frag).split())
    assert out == "I saw a post submitted by /u/foo earlier. The drama grew."


def test_fetch_entries_raises_on_non_xml(monkeypatch):
    from sources import base
    monkeypatch.setattr(base, "fetch_text", lambda url: "<html>unclosed")
    with pytest.raises(RuntimeError, match="non-feed"):
        base.fetch_entries("https://x")


def test_fetch_entries_raises_on_html_page(monkeypatch):
    from sources import base
    monkeypatch.setattr(base, "fetch_text",
                        lambda url: "<html><body>blocked</body></html>")
    with pytest.raises(RuntimeError, match="non-feed"):
        base.fetch_entries("https://x")
```

- [ ] **Step 8: Implement the RSS layer** — in `sources/base.py`, DELETE `get_json` and `to_obj`; keep `import time`, `import requests`; add `from xml.etree import ElementTree` and `from types import SimpleNamespace` (if not present); add:

```python
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
# the real feed trailer is exactly "submitted by /u/<name> [link] [comments]"
# at the end — requiring the immediate terminals means prose that merely says
# "submitted by /u/xxx" mid-story is never eaten
_TRAILER = re.compile(r"\s*submitted by\s+/u/\S+\s*\[link\]\s*\[comments\]\s*$",
                      re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")

_last_fetch = 0.0  # module-level politeness gap between Reddit hits


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
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.text
        status = resp.status_code
        if status == 429:            # rate limited: back off hard
            time.sleep(45 * (attempt + 1))
            continue
        if status in (500, 502, 503):
            time.sleep(2 * (attempt + 1))
            continue
        break
    raise RuntimeError(
        f"Reddit request failed (HTTP {status}) for {url}. Set a descriptive "
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
```

In `config.py`: delete the `ASKREDDIT_MIN_SCORE = 100` line.

- [ ] **Step 9: Run tests to verify green**

Run: `python -m pytest tests/ -v`
Expected: 27 passed (6 subtitles + 21 base: 7 original + 6 clean_text regressions + 8 RSS). `grep -rn "get_json\|to_obj\|MIN_SCORE" *.py sources/ tests/` finds nothing.

- [ ] **Step 10: Live check (single request, no burst) and commit**

Run: `python -c "from sources.base import fetch_entries; es = fetch_entries('https://www.reddit.com/r/AmItheAsshole/hot.rss?limit=5'); print(len(es), 'entries;', es[0].kind, es[0].id, '|', es[0].title[:50])"`
Expected: ~5 entries, first is `t3` with a real id/title. (If 429: earlier probing tripped the rate limit — wait 5 minutes and retry once.)

```bash
git add config.py sources/base.py tests/test_base.py
git commit -m "fetch reddit via rss feeds, json is fingerprint-blocked"
```

---

## Self-review notes (spec ↔ plan)

- Spec §sources/base, reddit_text, askreddit, tts, subtitles, video, main → Tasks 3, 4, 5, 6, 2, 7, 8 respectively; hygiene → Task 1; README → Task 9. Niche presets table → Task 1 `NICHES`. Used-ID tracking → Task 3 + recorded in Task 8 after successful render only. Random bg offset → Task 7 `pick_offset`. Word-pop → horror preset `words_per_line=1`.
- Open behavior choices locked here: MP3 kept natively (no WAV transcode); center crop replaces the original hardcoded `crop=...:1080:40` offsets (works for any source resolution); `Arial` replaces `PT Sans` (guaranteed on Windows; both are config).
- Types cross-checked: `WordBoundary(word, start, end)` defined once in `subtitles.py`, imported by `tts.py`; `Story(id, title, text, url, niche)` defined once in `sources/base.py`; `fetch() -> Story | None` on both sources; `main.build_source` returns `ContentSource`.
