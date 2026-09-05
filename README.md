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

## Using it — works with Claude Code today

> **Compatibility:** this skill currently targets **Claude Code only**. The
> workflow itself (versioned contracts, CLI tools, file-based state) is
> model-agnostic by design, and support for more coding agents (Codex-class,
> Gemini-class, strong local models) is on the roadmap — but only Claude Code
> has walked the full path end to end so far.

**Start here — open this repo in Claude Code and paste:**

```
Read .claude/skills/channel-maker/SKILL.md and README.md, then walk me through
creating a YouTube channel in <your niche here> per the skill, starting at
Stage 0.
```

What happens next is a live, conversational walkthrough (see
`.claude/skills/channel-maker/SKILL.md`, which walks Stage 0 through Stage 10
plus the Ongoing episode loop, with a Stage 0.5 resume procedure for picking up
mid-channel). Claude runs the CLIs below and asks you for every real decision:

- **Stages 0–1** — environment bootstrap (Hermes + local model), channel
  intent, and a hard CEO-style interrogation of your channel thesis before
  anything is scaffolded.
- **Stages 2–3** — Hermes-driven niche research, video teardowns, and an
  opportunity map, ending at a human strategy gate.
- **Stages 4–7** — channel foundation, Script/Visual/Motion DNA discovery, and
  channel identity, each frozen only on your explicit sign-off.
- **Stages 8–10** — starter asset library, pilot production with real
  voiceover, human GO/REVISE/ABANDON review, and the `CHANNEL_READY`
  checklist.
- **Ongoing** — the episode loop that produces the channel's actual videos
  without ever touching the frozen channel version.

Resuming later is normal: reopen the repo, tell Claude your channel id, and it
reconstructs state from `channels/<id>/CHANNEL_STATE.json` and continues where
you stopped.

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

### Control panel (interactive)

`.venv/bin/python tools/dashboard/server.py --port 8420` starts a local-only
(127.0.0.1) control panel that stays open beside your Claude session while you
work. It is the creator dashboard — one glance answers *where are we, what's
next, what needs my eyes, is the machine healthy*:

- **Channel list + per-channel detail** — live workflow state, next action,
  and the full event log (every advance, freeze, review, and revision).
- **Unified review queue** — everything waiting on a human across niche
  opportunities, script examples, design exemplars, identity candidates, asset
  components, pilots, and episodes, each linking back to its evidence.
- **Wiki browsing** — channel memory pages (strategy, hypotheses, lessons)
  as they accumulate.
- **One-click gated actions** — freezes, reviews, and GO/REVISE calls run as
  buttons, but every one shells out to the exact same CLI with an explicit
  browser confirm step first. The panel never re-implements tool logic and
  never fabricates an approval.

Keep it open for the whole lifecycle: the skill's Stage 1.5 tells Claude to
start it right after scaffolding, and the per-channel contents fill in live as
stages complete.

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
