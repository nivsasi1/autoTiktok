# Phase B: Auto-Posting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the loop from rendered video to posted TikTok: captions, cookie-based upload behind an `Uploader` interface, per-account Windows scheduling, and a post history — two accounts (drama + horror) from day one.

**Architecture:** Phase A's render pipeline stays untouched; Phase B adds a `--post --account NAME` mode to main.py that captions the rendered video (`metadata.py`), uploads it (`uploader/` package, cookie implementation now, official API later behind the same ABC), logs the attempt (`post_log.py`), and parks failures in `outbox/`. Windows Task Scheduler (registered by `scripts/register_tasks.ps1`) is the only scheduler.

**Tech Stack:** Python 3.14, tiktok-uploader~=1.2 (selenium under the hood; Chrome present), Windows Task Scheduler via PowerShell 5.1, pytest.

**Spec:** `docs/superpowers/specs/2026-07-06-phase-b-autopost-design.md`

## Global Constraints

- New dependency limited to: `tiktok-uploader~=1.2`. Everything else stdlib.
- `tiktok_uploader` is imported LAZILY inside `CookieUploader.upload` only — render-only runs, dry-runs, and the test suite must never import selenium.
- Secrets/credentials: `cookies/` is gitignored; cookie file contents never printed, logged, or committed. Errors name the file path only.
- All new file writes use `encoding="utf-8"`; all artifact paths defined once in `config.py` (`OUTBOX_DIR="outbox"`, `POST_LOG_PATH="posts.jsonl"`).
- Branch: `feat/phase-b-autopost`. Commit style: short, humanized, one per green test cycle.
- The PowerShell script targets Windows PowerShell 5.1 (no `&&`, no ternary).
- Used-ID semantics unchanged: recorded at render time; `posts.jsonl` records upload outcomes separately.
- Render-only mode (`python main.py --niche X`) must behave exactly as today.

## Prerequisites (user-gated, coordinate when reached)

1. **Cookie files** (Task 7 live posting only): user exports `cookies/drama_main.txt` and `cookies/horror_main.txt` via a "Get cookies.txt LOCALLY"-style extension while logged into each account. NOT needed for unit tests or dry-runs.
2. **Task registration** (after the README ramp, user-initiated): running `scripts/register_tasks.ps1` is deliberately left to the user post-warm-up; Task 6 only verifies a register→list→remove cycle.

---

### Task 1: Config, dependency, hygiene

**Files:**
- Modify: `config.py` (append Phase B block), `.gitignore`, `requirements.txt`
- Test: `tests/test_config.py` (create)

**Interfaces:**
- Consumes: existing `NICHES`.
- Produces: `Account(niche: str, cookies_file: str, posts_per_day: int)` dataclass; `ACCOUNTS: dict[str, Account]` with keys `"drama_main"`, `"horror_main"`; `HASHTAGS: dict[niche, {"fixed": list[str], "pool": list[str]}]`; `CAPTION_TITLE_CHARS = 90`; `POST_JITTER_MAX_S = 900`; `OUTBOX_DIR = "outbox"`; `POST_LOG_PATH = "posts.jsonl"`. All later tasks import these.

- [ ] **Step 1: Write the failing test** — `tests/test_config.py`

```python
import config


def test_every_account_niche_exists():
    for name, acct in config.ACCOUNTS.items():
        assert acct.niche in config.NICHES, name


def test_every_account_niche_has_hashtags():
    for acct in config.ACCOUNTS.values():
        tags = config.HASHTAGS[acct.niche]
        assert len(tags["fixed"]) >= 3
        assert len(tags["pool"]) >= 4


def test_posting_paths_defined():
    assert config.OUTBOX_DIR == "outbox"
    assert config.POST_LOG_PATH == "posts.jsonl"
    assert config.CAPTION_TITLE_CHARS == 90
    assert config.POST_JITTER_MAX_S == 900
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: module 'config' has no attribute 'ACCOUNTS'`

- [ ] **Step 3: Append to `config.py`**

```python
# --- Phase B: posting ---
@dataclass
class Account:
    niche: str             # key into NICHES
    cookies_file: str      # cookies/<name>.txt, exported by the user
    posts_per_day: int     # informational; the schedule lives in Task Scheduler


ACCOUNTS = {
    "drama_main":  Account("drama",  "cookies/drama_main.txt",  2),
    "horror_main": Account("horror", "cookies/horror_main.txt", 2),
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
POST_LOG_PATH = "posts.jsonl"
```

- [ ] **Step 4: Hygiene** — append to `.gitignore`:

```
cookies/
outbox/
posts.jsonl
```

Append to `requirements.txt`: `tiktok-uploader~=1.2` and run `pip install -r requirements.txt`.

- [ ] **Step 5: Run tests green**

Run: `python -m pytest tests/test_config.py -v` → 3 passed. Full suite: `python -m pytest tests/ -q` → 56 passed.

- [ ] **Step 6: Commit**

```bash
git add config.py .gitignore requirements.txt tests/test_config.py
git commit -m "add posting config: accounts, hashtags, outbox paths"
```

---

### Task 2: metadata.py — captions

**Files:**
- Create: `metadata.py`
- Test: `tests/test_metadata.py`

**Interfaces:**
- Consumes: `config.HASHTAGS`, `config.CAPTION_TITLE_CHARS`; story objects with `.title` (duck-typed).
- Produces: `build_caption(story, niche: str, rng=None) -> str` — trimmed title + fixed hashtags + 2 sampled from the pool. `rng` accepts anything with `.sample` (defaults to the `random` module). Task 5 calls it.

- [ ] **Step 1: Write the failing tests** — `tests/test_metadata.py`

```python
import random
from types import SimpleNamespace

import config
from metadata import build_caption


def story(title):
    return SimpleNamespace(title=title)


def test_short_title_kept_and_tagged():
    cap = build_caption(story("Am I wrong?"), "drama", rng=random.Random(1))
    assert cap.startswith("Am I wrong? ")
    for tag in config.HASHTAGS["drama"]["fixed"]:
        assert tag in cap


def test_long_title_trimmed_at_word_boundary():
    long_title = "word " * 40   # 200 chars
    cap = build_caption(story(long_title.strip()), "drama",
                        rng=random.Random(1))
    head = cap.split(" #")[0]
    assert head.endswith("…")
    assert len(head) <= config.CAPTION_TITLE_CHARS + 1   # +1 for the ellipsis
    assert not head.rstrip("…").endswith("wor")          # no mid-word cut


def test_exactly_two_pool_tags_added():
    cap = build_caption(story("T"), "horror", rng=random.Random(7))
    tags = [w for w in cap.split() if w.startswith("#")]
    fixed = config.HASHTAGS["horror"]["fixed"]
    assert tags[:3] == fixed
    extra = tags[3:]
    assert len(extra) == 2
    assert all(t in config.HASHTAGS["horror"]["pool"] for t in extra)


def test_seeded_rng_is_deterministic():
    a = build_caption(story("T"), "drama", rng=random.Random(42))
    b = build_caption(story("T"), "drama", rng=random.Random(42))
    assert a == b
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_metadata.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'metadata'`

- [ ] **Step 3: Write `metadata.py`**

```python
import random

import config


def build_caption(story, niche: str, rng=None) -> str:
    """Title (trimmed at a word boundary) + fixed hashtags + 2 rotating."""
    rng = rng or random
    title = story.title
    if len(title) > config.CAPTION_TITLE_CHARS:
        cut = title[: config.CAPTION_TITLE_CHARS]
        idx = cut.rfind(" ")
        title = (cut[:idx] if idx > 0 else cut).rstrip() + "…"
    tags = config.HASHTAGS[niche]
    chosen = tags["fixed"] + rng.sample(tags["pool"], 2)
    return f"{title} {' '.join(chosen)}"
```

- [ ] **Step 4: Run green**

Run: `python -m pytest tests/test_metadata.py -v` → 4 passed.

- [ ] **Step 5: Commit**

```bash
git add metadata.py tests/test_metadata.py
git commit -m "add caption builder with per-niche hashtags"
```

---

### Task 3: post_log.py — post history

**Files:**
- Create: `post_log.py`
- Test: `tests/test_post_log.py`

**Interfaces:**
- Produces: `append_post(path: str, record: dict) -> None` (JSONL append, utf-8, `ensure_ascii=False`); `read_posts(path: str) -> list[dict]` (missing file → `[]`, corrupt lines skipped — same tolerance philosophy as `load_used_ids`). Task 5 calls `append_post`.

- [ ] **Step 1: Write the failing tests** — `tests/test_post_log.py`

```python
from post_log import append_post, read_posts


def test_roundtrip_accumulates(tmp_path):
    p = str(tmp_path / "posts.jsonl")
    append_post(p, {"story_id": "a", "ok": True})
    append_post(p, {"story_id": "b", "ok": False, "title": "עברית ok"})
    posts = read_posts(p)
    assert [r["story_id"] for r in posts] == ["a", "b"]
    assert posts[1]["title"] == "עברית ok"   # utf-8, not escaped


def test_missing_file_reads_empty(tmp_path):
    assert read_posts(str(tmp_path / "nope.jsonl")) == []


def test_corrupt_line_skipped(tmp_path):
    p = tmp_path / "posts.jsonl"
    p.write_text('{"story_id": "a"}\nnot json\n{"story_id": "b"}\n',
                 encoding="utf-8")
    assert [r["story_id"] for r in read_posts(str(p))] == ["a", "b"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_post_log.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'post_log'`

- [ ] **Step 3: Write `post_log.py`**

```python
import json


def append_post(path: str, record: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_posts(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            posts = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    posts.append(json.loads(line))
                except ValueError:   # tolerate a corrupt line
                    continue
            return posts
    except OSError:
        return []
```

- [ ] **Step 4: Run green**

Run: `python -m pytest tests/test_post_log.py -v` → 3 passed.

- [ ] **Step 5: Commit**

```bash
git add post_log.py tests/test_post_log.py
git commit -m "add jsonl post history"
```

---

### Task 4: uploader package

**Files:**
- Create: `uploader/__init__.py` (empty), `uploader/base.py`, `uploader/tiktok_cookies.py`
- Test: `tests/test_uploader.py`

**Interfaces:**
- Produces: `PostResult(ok: bool, detail: str)` dataclass; `Uploader` ABC with `upload(self, video_path: str, caption: str) -> PostResult`; `CookieUploader(cookies_file: str, account: str)` — raises `RuntimeError` at construction when the cookies file is missing (message names the file and the re-export procedure, never the contents); `upload()` never raises for upload failures — returns `ok=False` with the reason. Task 5 constructs `CookieUploader` and consumes `PostResult`.
- CRITICAL: `from tiktok_uploader.upload import upload_video` happens INSIDE `upload()` (lazy) — the suite and dry-runs must not import selenium.

- [ ] **Step 1: Write the failing tests** — `tests/test_uploader.py`

```python
import sys
from types import SimpleNamespace

import pytest

from uploader.base import PostResult, Uploader
from uploader.tiktok_cookies import CookieUploader


def make_uploader(tmp_path):
    cookies = tmp_path / "acct.txt"
    cookies.write_text("# netscape cookies", encoding="utf-8")
    return CookieUploader(str(cookies), "acct")


def fake_lib(monkeypatch, upload_video):
    mod = SimpleNamespace(upload_video=upload_video)
    monkeypatch.setitem(sys.modules, "tiktok_uploader", SimpleNamespace(upload=mod))
    monkeypatch.setitem(sys.modules, "tiktok_uploader.upload", mod)


def test_missing_cookies_raise_named_error(tmp_path):
    with pytest.raises(RuntimeError, match=r"acct.*not found|not found.*acct"):
        CookieUploader(str(tmp_path / "missing.txt"), "acct")


def test_upload_success(tmp_path, monkeypatch):
    up = make_uploader(tmp_path)
    fake_lib(monkeypatch, lambda *a, **kw: [])
    result = up.upload("out.mp4", "caption")
    assert result == PostResult(True, "uploaded")


def test_upload_reported_failure(tmp_path, monkeypatch):
    up = make_uploader(tmp_path)
    fake_lib(monkeypatch, lambda *a, **kw: ["out.mp4"])
    result = up.upload("out.mp4", "caption")
    assert result.ok is False
    assert "failure" in result.detail


def test_upload_exception_becomes_result(tmp_path, monkeypatch):
    up = make_uploader(tmp_path)

    def boom(*a, **kw):
        raise TimeoutError("browser died")

    fake_lib(monkeypatch, boom)
    result = up.upload("out.mp4", "caption")
    assert result.ok is False
    assert "TimeoutError" in result.detail


def test_uploader_is_abstract():
    with pytest.raises(TypeError):
        Uploader()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_uploader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'uploader'`

- [ ] **Step 3: Write `uploader/base.py`** (and empty `uploader/__init__.py`)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PostResult:
    ok: bool
    detail: str   # uploader message or error text


class Uploader(ABC):
    """One video in, one PostResult out. Implementations must not raise for
    upload failures — that is what PostResult.ok=False is for."""

    @abstractmethod
    def upload(self, video_path: str, caption: str) -> PostResult: ...
```

- [ ] **Step 4: Write `uploader/tiktok_cookies.py`**

```python
import os

from uploader.base import PostResult, Uploader

_COOKIE_HELP = (
    "export cookies while logged into that account: install a 'Get cookies.txt "
    "LOCALLY' browser extension, open tiktok.com, export, save as {path}")


class CookieUploader(Uploader):
    """tiktok-uploader (browser cookies) implementation.

    ToS-gray — see the README risk note. Swapped for the official API
    implementation once the app audit is approved."""

    def __init__(self, cookies_file: str, account: str):
        if not os.path.exists(cookies_file):
            raise RuntimeError(
                f"cookies file {cookies_file} for account '{account}' not "
                "found — " + _COOKIE_HELP.format(path=cookies_file))
        self.cookies_file = cookies_file
        self.account = account

    def upload(self, video_path: str, caption: str) -> PostResult:
        # lazy import: selenium only loads when a real upload happens
        from tiktok_uploader.upload import upload_video
        try:
            failed = upload_video(video_path, description=caption,
                                  cookies=self.cookies_file)
        except Exception as exc:
            return PostResult(False, f"{exc.__class__.__name__}: {exc}")
        if failed:
            return PostResult(False, f"tiktok-uploader reported failure: {failed}")
        return PostResult(True, "uploaded")
```

- [ ] **Step 5: Run green**

Run: `python -m pytest tests/test_uploader.py -v` → 5 passed. Confirm no selenium import leaks: `python -c "import tests, uploader.tiktok_cookies, sys; assert 'selenium' not in sys.modules; print('lazy ok')"`

- [ ] **Step 6: Commit**

```bash
git add uploader/ tests/test_uploader.py
git commit -m "add uploader interface and cookie implementation"
```

---

### Task 5: main.py --post wiring

**Files:**
- Modify: `main.py` (full new content below)
- Test: `tests/test_publish.py`

**Interfaces:**
- Consumes: everything above — `config.ACCOUNTS/OUTBOX_DIR/POST_LOG_PATH/POST_JITTER_MAX_S`, `metadata.build_caption`, `post_log.append_post`, `CookieUploader`, `PostResult`.
- Produces: CLI `python main.py --post --account NAME [--dry-run]`; helper `_publish(story, account_name: str, dry_run: bool) -> int` (unit-tested with a fake uploader via `monkeypatch.setattr(main, "CookieUploader", ...)`). Render-only mode unchanged.

- [ ] **Step 1: Write the failing tests** — `tests/test_publish.py`

```python
from types import SimpleNamespace

import config
import main
from uploader.base import PostResult
from post_log import read_posts


def story():
    return SimpleNamespace(id="s1", title="A tale", url="u", niche="drama")


def redirect_paths(tmp_path, monkeypatch, with_video=True):
    monkeypatch.setattr(config, "POST_LOG_PATH", str(tmp_path / "posts.jsonl"))
    monkeypatch.setattr(config, "OUTBOX_DIR", str(tmp_path / "outbox"))
    monkeypatch.setattr(config, "OUTPUT_VID_PATH", str(tmp_path / "out.mp4"))
    if with_video:
        (tmp_path / "out.mp4").write_bytes(b"video")


class FakeUploader:
    def __init__(self, result):
        self.result = result

    def upload(self, video_path, caption):
        return self.result


def test_dry_run_logs_and_never_uploads(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch, with_video=False)
    monkeypatch.setattr(
        main, "CookieUploader",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("constructed")))
    assert main._publish(story(), "drama_main", dry_run=True) == 0
    posts = read_posts(config.POST_LOG_PATH)
    assert posts[0]["ok"] is None and posts[0]["story_id"] == "s1"


def test_success_logs_and_keeps_video(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "CookieUploader",
                        lambda *a, **kw: FakeUploader(PostResult(True, "uploaded")))
    assert main._publish(story(), "drama_main", dry_run=False) == 0
    assert read_posts(config.POST_LOG_PATH)[0]["ok"] is True
    assert (tmp_path / "out.mp4").exists()


def test_failure_parks_video_in_outbox(tmp_path, monkeypatch):
    redirect_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "CookieUploader",
                        lambda *a, **kw: FakeUploader(PostResult(False, "boom")))
    assert main._publish(story(), "drama_main", dry_run=False) == 1
    assert not (tmp_path / "out.mp4").exists()
    assert (tmp_path / "outbox" / "s1.mp4").read_bytes() == b"video"
    caption = (tmp_path / "outbox" / "s1.txt").read_text(encoding="utf-8")
    assert caption.startswith("A tale")
    assert read_posts(config.POST_LOG_PATH)[0]["ok"] is False
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_publish.py -v`
Expected: FAIL — `AttributeError: module 'main' has no attribute '_publish'`

- [ ] **Step 3: Replace `main.py` with**

```python
import argparse
import os
import random
import shutil
import sys
import time
from pathlib import Path

import config
import metadata
import post_log
import subtitles
import tts
import video
from sources.askreddit import AskRedditSource
from sources.base import load_used_ids, record_used_id
from sources.reddit_text import RedditTextSource
from uploader.tiktok_cookies import CookieUploader


def build_source(niche: str, preset, used_ids):
    if niche == "askreddit":
        return AskRedditSource(preset, used_ids)
    return RedditTextSource(niche, preset, used_ids)


def _publish(story, account_name: str, dry_run: bool) -> int:
    """Caption + upload the rendered video; park it in the outbox on failure."""
    account = config.ACCOUNTS[account_name]
    caption = metadata.build_caption(story, account.niche)
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "account": account_name,
              "niche": account.niche, "story_id": story.id, "title": story.title}
    if dry_run:
        print(f"dry-run: would post {config.OUTPUT_VID_PATH}")
        print(f"caption: {caption}")
        post_log.append_post(config.POST_LOG_PATH,
                             {**record, "ok": None, "detail": "dry-run"})
        return 0
    uploader = CookieUploader(account.cookies_file, account_name)
    result = uploader.upload(config.OUTPUT_VID_PATH, caption)
    post_log.append_post(config.POST_LOG_PATH,
                         {**record, "ok": result.ok, "detail": result.detail})
    if not result.ok:
        os.makedirs(config.OUTBOX_DIR, exist_ok=True)
        parked = os.path.join(config.OUTBOX_DIR, f"{story.id}.mp4")
        shutil.move(config.OUTPUT_VID_PATH, parked)
        Path(config.OUTBOX_DIR, f"{story.id}.txt").write_text(
            caption, encoding="utf-8")
        print(f"upload failed ({result.detail}); video parked at {parked}")
        return 1
    print(f"posted to {account_name}: {caption[:60]}")
    return 0


def main() -> int:
    # redirected stdout defaults to cp1252 on Windows; emoji in story titles
    # would crash prints once a scheduler logs to a file
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Reddit story -> TikTok video")
    parser.add_argument("--niche", choices=sorted(config.NICHES))
    parser.add_argument("--post", action="store_true",
                        help="upload to TikTok after rendering")
    parser.add_argument("--account", choices=sorted(config.ACCOUNTS),
                        help="account to post as (implies its niche)")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --post: render and caption, skip the upload")
    args = parser.parse_args()

    if args.post:
        if not args.account:
            parser.error("--post requires --account")
        account = config.ACCOUNTS[args.account]
        niche = account.niche
        if not args.dry_run and not os.path.exists(account.cookies_file):
            print(f"error: cookies file {account.cookies_file} for "
                  f"'{args.account}' missing — see README 'Cookie export'")
            return 1
        if not args.dry_run:
            # human-irregular timing on top of Task Scheduler's random delay
            time.sleep(random.uniform(0, config.POST_JITTER_MAX_S))
    else:
        niche = args.niche or config.DEFAULT_NICHE
    preset = config.NICHES[niche]

    if not os.path.exists(config.INPUT_VID_PATH):
        print(f"error: background clip {config.INPUT_VID_PATH} not found "
              "(see README for a source)")
        return 1

    used_ids = load_used_ids(config.STATE_PATH)
    story = build_source(niche, preset, used_ids).fetch()
    if story is None:
        print(f"no qualifying {niche} post right now — try again later")
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

    try:
        record_used_id(config.STATE_PATH, story.id)
    except OSError as exc:
        # the video is already rendered — don't lose it over a state hiccup
        print(f"warning: couldn't update {config.STATE_PATH} ({exc}); "
              "this story may be picked again next run")

    if args.post:
        return _publish(story, args.account, args.dry_run)
    print(f"done -> {config.OUTPUT_VID_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run green + regression**

Run: `python -m pytest tests/ -q` → 67 passed (56 + 4 metadata + 3 post_log... adjust to actual count; all green, zero selenium imports). Sanity: `python main.py --help` shows `--post/--account/--dry-run`; `python main.py --post` errors with "requires --account".

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_publish.py
git commit -m "wire --post mode: caption, upload, outbox, history"
```

---

### Task 6: Scheduler script + README

**Files:**
- Create: `scripts/register_tasks.ps1`
- Modify: `README.md` (append Auto-posting section)

- [ ] **Step 1: Write `scripts/register_tasks.ps1`**

```powershell
# Registers the autoTiktok posting schedule (Windows Task Scheduler).
# Run AFTER the README warm-up ramp. -Remove unregisters everything.
param([switch]$Remove)

$repo = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python).Source
# keep account names in sync with config.ACCOUNTS
$tasks = @(
    @{ Name = "autoTiktok drama_main 1";  Account = "drama_main";  At = "10:00" },
    @{ Name = "autoTiktok drama_main 2";  Account = "drama_main";  At = "18:30" },
    @{ Name = "autoTiktok horror_main 1"; Account = "horror_main"; At = "12:00" },
    @{ Name = "autoTiktok horror_main 2"; Account = "horror_main"; At = "20:30" }
)

if ($Remove) {
    foreach ($t in $tasks) {
        try { Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false -ErrorAction Stop }
        catch {}
    }
    Write-Host "autoTiktok tasks removed"
    exit 0
}

foreach ($t in $tasks) {
    $action = New-ScheduledTaskAction -Execute $python `
        -Argument "main.py --post --account $($t.Account)" `
        -WorkingDirectory $repo
    $trigger = New-ScheduledTaskTrigger -Daily -At $t.At
    $trigger.RandomDelay = "PT40M"   # 0-40 min drift, human-looking
    Register-ScheduledTask -TaskName $t.Name -Action $action `
        -Trigger $trigger -Force | Out-Null
    Write-Host "registered $($t.Name) at $($t.At) (+0-40min random)"
}
Write-Host "done — check with: Get-ScheduledTask -TaskName 'autoTiktok*'"
```

- [ ] **Step 2: Verify register→list→remove cycle (leaves nothing behind)**

Run in PowerShell:
`powershell -ExecutionPolicy Bypass -File scripts/register_tasks.ps1` → 4 registered lines.
`Get-ScheduledTask -TaskName "autoTiktok*" | Select-Object TaskName,State` → 4 tasks, Ready.
`powershell -ExecutionPolicy Bypass -File scripts/register_tasks.ps1 -Remove` → removed.
`Get-ScheduledTask -TaskName "autoTiktok*"` → errors/empty (nothing left registered).

- [ ] **Step 3: Append to README.md** (before the Roadmap section)

```markdown
## Auto-posting (Phase B)

**Risk, stated plainly:** upload uses browser cookies + automation
(`tiktok-uploader`), which violates TikTok's ToS. Detection risk is mitigated
(randomized times, modest cadence) but never zero. The official API swaps in
once its audit is approved.

### One-time setup per account
1. Log into the TikTok account in your browser.
2. Export cookies with a "Get cookies.txt LOCALLY"-style extension while on
   tiktok.com; save as `cookies/drama_main.txt` (resp. `horror_main.txt`).
   Cookies are credentials: the folder is gitignored — keep it that way.

### Warm-up ramp (do this before scheduling)
- Week one: post 2-3 videos per account manually in the app, browse a little —
  a fresh account that instantly posts on a robotic schedule is the classic
  shadowban recipe.
- Then: `python main.py --post --account drama_main --dry-run` (renders and
  shows the caption, uploads nothing).
- Then 2-3 watched live posts: `python main.py --post --account drama_main`.
- Only then register the schedule:
  `powershell -ExecutionPolicy Bypass -File scripts/register_tasks.ps1`
  (`-Remove` unregisters).

### Day to day
- History: `posts.jsonl` (one line per attempt).
- Failed uploads are parked in `outbox/<story_id>.mp4` + `.txt` (the caption) —
  post them by hand, cookies probably need re-exporting.
- Cookie expiry shows up as a clear "cookies file ... missing/failed" error.
```

- [ ] **Step 4: Commit**

```bash
git add scripts/register_tasks.ps1 README.md
git commit -m "add task scheduler script and posting runbook"
```

---

### Task 7: Integration dry-run + wrap-up

**Files:** none new (verification + PR)

- [ ] **Step 1: Full suite**

Run: `python -m pytest tests/ -q` → all green (67±, zero warnings).

- [ ] **Step 2: Live dry-run e2e (internet; vid.mp4 — if absent, generate `ffmpeg -y -f lavfi -i testsrc=duration=240:size=1280x720:rate=30 vid.mp4` and delete after)**

Run: `python main.py --post --account drama_main --dry-run`
Expected: real story fetched + rendered (Phase A prints), then `dry-run: would post out.mp4` + a caption with title + 5 hashtags; `posts.jsonl` gains one `"ok": null` record; NO cookies file needed, NO selenium import, NO upload.

- [ ] **Step 3: Render-only regression**

Run: `python main.py --help` → old usage intact. Confirm plain render mode prints `done -> out.mp4` (can reuse the Step 2 artifacts run).

- [ ] **Step 4: Push + PR**

```bash
git push -u origin feat/phase-b-autopost
gh pr create --title "Phase B: auto-posting with scheduler" --body "..."
```
PR body: decisions (cookie uploader behind Uploader ABC, two accounts, Task Scheduler), safety rails (dry-run, outbox, ramp), test counts, what's deferred (official API swap-in, live posting gated on user's cookie export + warm-up).

---

## Self-review notes (spec ↔ plan)

- Spec §interfaces → Tasks 1 (config), 2 (metadata), 3 (post_log), 4 (uploader), 5 (main flow); §scheduling → Task 6; §testing → per-task TDD + Task 7 dry-run e2e; §hygiene → Task 1; README/ramp → Task 6.
- Live posting deliberately NOT in the plan's automated steps — it needs the user's cookie export and warm-up (Prerequisites); the plan ends at a verified dry-run.
- Type consistency checked: `PostResult(ok, detail)` and `CookieUploader(cookies_file, account)` identical in Tasks 4/5; `_publish(story, account_name, dry_run) -> int` matches tests; config names (`OUTBOX_DIR`, `POST_LOG_PATH`, `CAPTION_TITLE_CHARS`, `POST_JITTER_MAX_S`) uniform across Tasks 1/2/5.
- Exact suite counts in Steps may drift ±1-2 from reality; the binding requirement is "all green".
