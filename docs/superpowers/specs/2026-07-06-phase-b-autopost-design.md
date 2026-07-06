# autoTiktok — Phase B: auto-posting + scheduler

Date: 2026-07-06
Status: approved

## Context

Phase A produces finished videos (`python main.py --niche X` → out.mp4) but posting
is manual. Phase B closes the loop: captions, TikTok upload, per-account
scheduling, and a post history — on two accounts from day one (drama + horror).

Upload landscape (researched 2026-07): TikTok's official Content Posting API
requires an app audit (2-4 weeks, multiple rounds); unaudited apps can only post
SELF_ONLY/private. The unofficial `tiktok-uploader` package (cookie-based browser
automation) is actively maintained and works today, but violates TikTok ToS and
carries a real shadowban/ban risk. Decision: ship the cookie uploader now behind
an `Uploader` interface, submit the official API audit in parallel, and swap
implementations when approved — the same pattern that carried the Reddit pivots.

## Decisions (locked with user)

1. **Upload**: cookie-based `tiktok-uploader` now; official API later behind the
   same interface. Ban risk accepted and mitigated (jitter, modest cadence,
   warm-up ramp), never zero.
2. **Scheduler**: Windows Task Scheduler, registered by a one-shot script; a
   `--post` mode on main.py is the unit of execution.
3. **Accounts**: two from day one — drama + horror — each with its own cookies
   file, schedule, and cadence (default 2 posts/day each). Accounts are config
   data; adding more is not a code change.
4. **Captions**: per-niche templates — trimmed story title + fixed hashtag set +
   2 rotating from a pool (so captions vary). AI captions deferred to Phase D.
5. **Safety rails** (designer's addition): `--dry-run` flag, outbox for failed
   uploads, README warm-up ramp (week one: dry-runs + a few watched live posts
   before registering the tasks).

## Architecture

```
autoTiktok/
  uploader/
    __init__.py
    base.py              # PostResult + Uploader ABC
    tiktok_cookies.py    # CookieUploader (tiktok-uploader package)
  metadata.py            # build_caption(story, niche) -> str
  post_log.py            # append/read posts.jsonl
  main.py                # + --post --account NAME [--dry-run]
  config.py              # + Account dataclass, ACCOUNTS, HASHTAGS, jitter
  scripts/register_tasks.ps1   # register/remove per-account scheduled tasks
  cookies/<account>.txt  # user-exported, gitignored
  outbox/                # failed uploads parked here, gitignored
  posts.jsonl            # post history, gitignored
```

### Interfaces

```python
# uploader/base.py
@dataclass
class PostResult:
    ok: bool
    detail: str            # uploader message / error text

class Uploader(ABC):
    @abstractmethod
    def upload(self, video_path: str, caption: str) -> PostResult: ...
```

```python
# config.py
@dataclass
class Account:
    niche: str             # key into NICHES
    cookies_file: str      # cookies/<name>.txt
    posts_per_day: int

ACCOUNTS = {
    "drama_main":  Account("drama",  "cookies/drama_main.txt",  2),
    "horror_main": Account("horror", "cookies/horror_main.txt", 2),
}
HASHTAGS = {niche: {"fixed": [...3...], "pool": [...6+...]}}
CAPTION_TITLE_CHARS = 90      # trim titles at a word boundary
POST_JITTER_MAX_S = 900       # extra 0-15min random sleep before posting
```

- `metadata.build_caption(story, niche) -> str`: title trimmed at a word
  boundary to CAPTION_TITLE_CHARS, then fixed hashtags + 2 random from the pool.
  Randomness injectable for tests.
- `post_log.append_post(path, record: dict)` / `read_posts(path) -> list[dict]`:
  JSONL, utf-8, one record per attempt:
  `{ts, account, niche, story_id, title, ok, detail}`.
- `CookieUploader(cookies_file)` wraps `tiktok_uploader.upload_video`; missing
  or expired cookies produce a RuntimeError naming the account's cookies file
  and the re-export steps.

### Flow (`python main.py --post --account drama_main`)

1. Resolve account → niche/cookies; fail fast with a clear error if the cookies
   file is missing.
2. Sleep `random.uniform(0, POST_JITTER_MAX_S)` (skipped with `--dry-run`) —
   scheduled-task time + random delay + this jitter ≈ human-irregular timing.
3. Existing Phase A pipeline renders for that niche (unchanged).
4. `build_caption(story, niche)`.
5. `--dry-run`: print the caption + video path, log with `ok=None`, stop.
   Otherwise `uploader.upload(...)`.
6. Failure → move video + caption to `outbox/<story_id>.mp4/.txt`, log, exit 1
   (Task Scheduler surfaces the failure). Success → log, done. No auto-retry —
   the next scheduled run is the retry.
7. Plain `python main.py --niche X` (render-only) keeps working unchanged.

### Scheduling

`scripts/register_tasks.ps1` registers 2 daily triggers per account (staggered
between accounts, e.g. drama 10:00/18:30, horror 12:00/20:30) with
RandomDelay=40min, action `python main.py --post --account <name>` in the repo
directory. `-Remove` unregisters everything. Runs as the current user, no
elevation. Windows Task Scheduler owns persistence/reboots; nothing daemonizes.
Serialized per machine: the staggering + Phase A's single-instance assumption
(documented) — two tasks never fire within an hour of each other by
construction.

## Error handling

- Cookies missing/expired: RuntimeError names account, file, and the re-export
  procedure (browser extension → cookies/<account>.txt).
- Upload failure: outbox parking + loud log + exit 1; artifacts never lost.
- Reddit/TTS/render failures: Phase A behavior unchanged (no post attempted,
  used-ID not consumed for un-rendered stories).
- Used-ID stays recorded at render time; posts.jsonl records upload outcomes
  separately (a story is consumed once rendered, even if its upload fails —
  the outbox copy is the recovery path, not a re-render).

## Testing

- Unit (no network): build_caption (trim boundary, hashtag counts, injected
  randomness), post_log roundtrip, account resolution + missing-cookies error,
  main --post flow with a fake Uploader (success/failure/outbox/dry-run paths).
- Integration: `--dry-run` end-to-end (live Reddit + TTS + render, no upload).
- Live ramp (manual, with user): 2-3 watched posts per account before
  registering scheduled tasks.

## Dependencies

`tiktok-uploader~=1.2` (brings selenium; requires Chrome — present on this
machine). Everything else stdlib.

## Repo hygiene

`.gitignore` += `cookies/`, `outbox/`, `posts.jsonl`. README: cookie export
walkthrough, ramp-up protocol, task registration, ToS-risk disclosure.

## Deferred

Official API audit submission (user does the form; `ApiUploader` lands behind
the same interface when approved), per-account proxies, analytics, AskReddit
account, AI captions (Phase D).
