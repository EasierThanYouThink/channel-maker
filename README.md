# Channel Maker

A Claude Code skill and its supporting engine for taking a YouTube channel from
a bare idea through a fully-specified, evidence-backed pilot: niche/market
research, a channel foundation (audience/promise/personality/boundaries),
Script/Visual/Motion DNA discovery, a starter asset library, and a pilot
lifecycle (plan → production → human review → freeze), ending at
`CHANNEL_READY`. Every irreversible step — a domain freeze, an exemplar or
component review, a pilot GO/REVISE/ABANDON_DIRECTION call — requires a real,
non-fabricated human decision reference, enforced in code.

## Install

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

You'll also need [Hermes Agent](https://hermes-agent.nousresearch.com) and a
local model for niche/market research (see Stage 0 of the skill below) —
Hermes does the public web research; nothing here has its own scraper.

## Using it

Open this repo in Claude Code and invoke the `channel-maker` skill (see
`.claude/skills/channel-maker/SKILL.md`, which walks Stage 0 through Stage 9).
It's a live, conversational walkthrough — Claude runs the CLIs below and asks
you for every real decision (strategy selection, DNA freezes, reviews, the
pilot GO/REVISE/ABANDON_DIRECTION call).

You can also run any tool directly, e.g.:

```
.venv/bin/python tools/init_channel.py my-channel --name "My Channel" \
  --niche-primary "..." --archetype ILLUSTRATED_EXPLAINER \
  --creation-mode ORIGINAL --renderer remotion
.venv/bin/python tools/validate_channel.py channels/my-channel
```

### Dashboard

`.venv/bin/python tools/dashboard/server.py --port 8420` starts a local-only
(127.0.0.1) control panel: channel list, per-channel state/next-action/event
log, wiki browsing, and a unified review queue. It shells out to the exact
same CLIs, never re-implementing their logic; gated actions require an
explicit confirm step in the browser.

### Rendering

Stage 8 (pilot production) doesn't assume a specific rendering pipeline — see
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
