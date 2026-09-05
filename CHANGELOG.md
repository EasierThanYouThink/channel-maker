# Changelog

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
