# autoTiktok — Self-healing posting + status

Date: 2026-07-07
Status: approved (user asked for "more automatic")

## Context

Failed uploads park in `outbox/` and wait for a human. In practice (live
2026-07-06/07): cookie problems parked four videos that would have sat
forever. The scheduler should retry them itself, and the user should be able
to see the whole system's state in one command.

## Decisions

1. **Outbox entries get metadata.** Parking (upload failure, or part 2 pulled
   after part 1 failed) writes `<stem>.json` next to the video: account,
   niche, story id/title/url, part, caption, `attempts` counter. The `.txt`
   caption stays for humans. Legacy sidecar-less files are never auto-touched.
2. **One post per run, self-healing priority.** A `--post` run attempts
   exactly one upload, in order: queued part 2 -> oldest retryable outbox
   entry (sidecar matches the account, `attempts < 3`, `_p1` before `_p2`
   within a story) -> fresh story. A retried failure increments `attempts`
   and stays parked; after 3 attempts it's manual-only (visible in
   `--status`). One-per-run keeps the posting cadence TikTok-safe while the
   backlog drains over the schedule.
3. **Success cleanup**: a posted outbox entry deletes its video + sidecar +
   txt.
4. **Dry runs report** ("would retry outbox/x_p1.mp4, attempt 2/3") and
   change nothing.
5. **`python main.py --status`**: per-account login state (profile dir /
   cookies file), queue contents, outbox contents (with attempts and
   retryable flag), last 5 posts.jsonl records. Read-only, no network.
6. New module `outbox.py` (park / next_retry / bump / clear); `_publish`
   and `_park_part2` route their parking through it. `MAX_UPLOAD_RETRIES = 3`
   in config.

## Testing

Unit: outbox round-trip, account filter, attempts cap, p1-before-p2 order,
legacy files skipped; flow: outbox retried before a new story is fetched,
failure increments attempts, dry-run leaves state; status smoke (captured
stdout). Live: --status against the real repo state.

## Non-goals

Multi-post drain per run, GUI outbox panel, AI story source (own spec).
