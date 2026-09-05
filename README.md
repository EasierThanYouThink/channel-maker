# Channel Maker

A Claude Code skill and its supporting engine for taking a YouTube channel from
a bare idea through a fully-specified, evidence-backed pilot — then keeps
producing the channel's actual videos. V1 is CREATE-only and niche-driven:
niche/market research, video teardowns, a channel foundation
(audience/promise/personality/boundaries), Script/Visual/Motion DNA discovery,
channel identity (logo + description), a starter asset library, and a pilot
lifecycle (plan → production → human review → freeze), ending at
`CHANNEL_READY` — followed by a repeatable Episode Production loop that never
bumps the channel version. Every irreversible step — a domain freeze, an
exemplar/candidate/component review, a pilot or episode GO/REVISE/ABANDON call
— requires a real, non-fabricated human decision reference, enforced in code.

## Demo

A 14-second 1080p render in the style this workflow produces (bold kinetic
typography hook — one of the approved headline directions):

<video src="https://github.com/user-attachments/assets/e0c09a15-ec66-4430-91aa-c5fdb87bacb5" controls width="640"></video>

## Install (Windows / macOS / Linux)

```
python tools/setup.py
```

Creates `.venv`, installs `requirements.txt`, and reports the external-services
status. Details per OS: [`docs/SETUP.md`](docs/SETUP.md). Verify with
`python tools/check.py` (venv activated).

You'll also need [Hermes Agent](https://hermes-agent.nousresearch.com) and a
local model for niche/market research (see Stage 0 of the skill below) —
Hermes does the public web research; nothing here has its own scraper.

## Using it

Open this repo in Claude Code and invoke the `channel-maker` skill (see
`.claude/skills/channel-maker/SKILL.md`, which walks Stage 0 through Stage 10
plus the Ongoing episode loop, with a Stage 0.5 resume procedure for picking up
mid-channel). It's a live, conversational walkthrough — Claude runs the CLIs
below and asks you for every real decision (strategy selection, DNA freezes,
reviews, the pilot GO/REVISE/ABANDON_DIRECTION call).

You can also run any tool directly, e.g.:

```
.venv/bin/python tools/init_channel.py my-channel --name "My Channel" \
  --niche-primary "..." --archetype ILLUSTRATED_EXPLAINER \
  --renderer remotion
.venv/bin/python tools/validate_channel.py channels/my-channel
```

### Voice

Pilots and episodes are voice-first: `tools/voiceover.py synthesize` renders
narration fully offline (Piper TTS, voice model auto-downloaded on first use)
plus measured timing evidence, and `tools/voiceover.py validate` gates the
result against the target duration before any scene is built. One voice per
channel, picked once and reused.

### Dashboard

`.venv/bin/python tools/dashboard/server.py --port 8420` starts a local-only
(127.0.0.1) control panel: channel list, per-channel state/next-action/event
log, wiki browsing, and a unified review queue. It shells out to the exact
same CLIs for gated decisions, never re-implementing their logic; gated
actions require an explicit confirm step in the browser.

### Rendering

Stage 9 (pilot production) doesn't assume a specific rendering pipeline — see
[`docs/RENDER_CONTRACT.md`](docs/RENDER_CONTRACT.md) for the evidence contract
any renderer must satisfy.

## Verify

```
.venv/bin/python tools/check.py
```

Runs schema/channel/memory/niche-intelligence validation and the full pytest
suite.

## License

MIT — see [LICENSE](LICENSE).
