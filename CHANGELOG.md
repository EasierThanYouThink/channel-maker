# Changelog

## v0.2.2 — pre-public security and privacy hardening

Backward-compatible for documented CLIs and channel packages. The dashboard's
internal mutation endpoint now requires same-origin proof available from its
served page rather than accepting direct unauthenticated requests.

- Generated channel packages are ignored by Git while the repository placeholder
  remains tracked, preventing accidental publication of local channel data.
- Dashboard writes require a per-process anti-forgery token, JSON content, and a
  loopback same-origin request whenever an Origin header is supplied.
- Piper model and configuration downloads use an immutable upstream revision,
  verify pinned SHA-256 hashes, and install atomically only after verification.

## v0.2.1 — Windows portability and observable CI

Backward-compatible: logical Hermes job IDs and all documented CLI commands
are unchanged; existing POSIX queue records remain usable without migration.

- Human-gated CLIs now treat end-of-input as non-interactive, so Windows null
  stdin produces the normal `--yes` requirement instead of an uncaught
  `EOFError`.
- Hermes queue records, responses, and runtime metadata use bounded,
  SHA-256-derived filenames on every OS while preserving their descriptive
  colon-separated job IDs inside JSON and at the CLI boundary.
- The complete Python 3.11–3.14 matrix now runs on Ubuntu, Windows, and macOS
  without fail-fast cancellation, using current GitHub Action runtimes.

## v0.2.0 — tighter lifecycle, proven media, isolated tests

Backward-compatible: existing channels migrate automatically on their next
read or write (15-state history folds into the 10-state vocabulary, event
evidence preserved); nothing needs manual rework.

- CM1 lifecycle collapsed 15 → 10 states with identical gate semantics:
  the opportunity map folds into the gated strategy edge, Visual + Motion
  DNA merge into one design stage, the library and pilot plan arrive as
  evidence on the production edge, and freezing leads straight to
  `CHANNEL_READY` through the second human gate.
- Production media is now probed, not just present: voiceover WAV files
  fully decode, render MP4 files prove an `ftyp` container, PNG stills
  prove signature + IHDR — all stdlib-only, no new dependencies. Corrupt
  media blocks a GO.
- System proofs are enforced artifacts: an approved composed frame (visual
  domains together, grounded in approved exemplars) and an approved
  narrated motion sample (clip bound to an existing narration ref) are
  required before design stages count as ready, and both surface in the
  dashboard review queue.
- Skill walkthrough runs fully isolated in a seeded tmp repository root:
  nothing touches the checkout's `channels/` tree.
- Dead artifact-schema entries pruned to the four live Stage-9 types, so
  unknown types fail with a clean error instead of a missing-file error.

## v0.1.0 — first public release

Channel Maker as a standalone repo: a Claude Code skill plus its supporting
engine for taking a YouTube channel from a bare niche idea to `CHANNEL_READY`
and producing ongoing episodes afterward.

- CM1 channel lifecycle: `CHANNEL_INIT` through `CHANNEL_READY` with legal
  transitions, human gates, block/resume, bounded pilot revision, atomic
  persistence, and chained history.
- Niche intelligence: offline evidence contracts, Hermes-driven collection
  queue with human-reviewed import, video teardowns, observations →
  hypotheses → opportunities, same-channel relative-views metric.
- Channel foundation, Script/Visual/Motion DNA discovery with human-gated
  domain freezes, channel identity (logo + description), starter asset
  library, pilot plan/production/review/freeze, `CHANNEL_READY` checklist.
- Ongoing Episode Production loop that never bumps the channel version.
- Local-first voice: offline Piper TTS with measured timing evidence and a
  duration-vs-target validation gate.
- Local dashboard (127.0.0.1) with a unified review queue and a whitelisted,
  confirm-gated action dispatcher.
- V1 is CREATE-only; CLONE support is preserved on `archive/clone-mode-capable`.
