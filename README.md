# Channel Maker

A complete YouTube channel-making methodology for your coding agent, built on
one composable skill and an evidence-first engine that enforces it. This idea
got to my mind, when Youtube announced that for their Shorts monetization you
need atleast 20 million views in the past 90 days. Luckily they will
implement this change in the year 2027 (which is in three months). 
This our last chance to build successful
channels, then if they implement this, it won't really bother us.

> [!WARNING]
> **Public Beta:** Channel Maker is under active development, It hasn't
> been tested by active usage - that is why we need the world to test it. Expect rough
> edges and workflow changes. Back up channel projects before upgrading, and
> report problems through GitHub Issues. Feedback and contributions from the
> Claude developer community are welcome.

<video src="https://github.com/user-attachments/assets/e0c09a15-ec66-4430-91aa-c5fdb87bacb5" controls width="640"></video>

Table of Contents

- [How it works](#how-it-works)
- [Getting Started](#getting-started)
  - [Claude Code](#claude-code)
  - [Other coding agents](#other-coding-agents)
- [The Channel-Making Workflow](#the-channel-making-workflow)
- [Control panel](#control-panel-interactive)
- [Voice](#voice)
- [Rendering](#rendering)
- [Tools it stands on](#tools-it-stands-on)
- [What's Inside](#whats-inside)
- [Philosophy](#philosophy)
- [Contributing](#contributing)
- [Updating](#updating)
- [Verify](#verify)
- [FAQ](#faq)
- [License](#license)

## How it works

It starts the moment you tell your coding agent you want a YouTube channel. It
doesn't jump to generating a logo or a script. Instead, it interrogates your
channel thesis like a skeptical CEO — why this channel, for whom, what every
single video promises — and only scaffolds when the thesis survives.

Then it walks the full lifecycle with you in sections short enough to actually
read and decide on: Hermes-driven niche research and video teardowns, an
opportunity map, a human strategy gate, foundation, Script/Visual/Motion DNA
discovery, identity, a starter asset library, and a pilot built voice-first
with measured timing evidence. Each stage ends at a gate only you can open.

After `CHANNEL_READY`, the same skill keeps producing the channel's actual
videos through an episode loop that never touches the frozen channel version.
And because channel state lives in files, not in the conversation, any fresh
session resumes exactly where you stopped.

## Getting Started

> **What you'll need:** 30–60 minutes on a first run (mostly the ~6.6GB local
> research-model download), ~7GB of disk, everything on your own machine — no
> API keys or cloud bill. A GPU is optional, but strongly recommended for faster
> Ornith research; Claude asks you to choose GPU or CPU during setup. Details per OS:
> [`docs/SETUP.md`](docs/SETUP.md).

### Claude Code

No setup work on your side — Claude does all of it. Three steps:

**1 — Create a folder** for your channel project (e.g. `Claude_Channel`) and
open a terminal inside it.

**2 — Start Claude Code** from that folder:

```
claude
```

**3 — Paste this prompt** (best results with Opus 5 on high effort):

```
Clone https://github.com/EasierThanYouThink/channel-maker.git into this
folder, then read .claude/skills/channel-maker/SKILL.md and README.md, run
the full environment setup (venv, dependencies, service checks), and walk me
through creating a YouTube channel in <your niche here> per the skill,
starting at Stage 0.
```

That's it — Claude clones the repo, installs everything, checks the
machine (Hermes Agent for public web research, a local model, voice, Node),
and starts the channel walkthrough with you. Nothing here has its own
scraper; public web research goes through Hermes (see Stage 0 of the skill).

### Other coding agents

The workflow itself is harness-agnostic by design — versioned contracts, CLI
tools, file-based state, no vendor lock-in. But only Claude Code has walked the
full path end to end so far. Codex-class, Gemini-class, and strong local models
are on the roadmap; until then, expect rough edges anywhere outside Claude
Code and report them.

## The Channel-Making Workflow

The skill checks the machine's own `next` output before every step, so the
agent always knows what's legal now. The stages:

- **resume** — Activates at every session start. Reconstructs state from
  `CHANNEL_STATE.json`, dry-runs the next edge, never re-runs scaffolds.
- **intent** — Activates with a niche. CEO-interrogates the channel thesis,
  writes it down, scaffolds the Channel Package.
- **niche-intelligence** — Activates with intent. Hermes-driven public
  research through a reviewed import queue, plus video teardowns and a
  relative-views metric. No private analytics, ever.
- **opportunity-map** — Activates with evidence. Converts findings into
  strategic options and crosses the first human gate at strategy selection.
- **foundation** — Activates with strategy. Audience, promise, personality,
  boundaries, and what the channel deliberately avoids.
- **script-dna** — Activates with foundation. Hook philosophy, narrator voice,
  density, structure — frozen only on your sign-off.
- **visual/motion-dna** — Activates with script DNA. Candidate exemplars,
  narrowing loops, per-domain freezes across five visual domains plus motion.
- **identity** — Activates with frozen DNA. Logo and About-page bio in the
  channel's own voice.
- **starter-library** — Activates with identity. Code-first components, only
  what the pilot actually needs — never a speculative catalog.
- **pilot** — Activates with the library. Voice-first production (script →
  offline TTS → measured timings → visual beats → render → evaluation
  evidence), human GO/REVISE/ABANDON review, version-bumping freeze.
- **readiness** — Activates with a GO'd pilot. The 12-item `CHANNEL_READY`
  checklist; nothing writes until everything passes.
- **episodes** — Activates after `CHANNEL_READY`, forever. Same production
  rigor as the pilot, no version bump, no state-machine involvement.

## Control panel (interactive)

`.venv/bin/python tools/dashboard/server.py --port 8420` starts a local-only
(127.0.0.1) panel that stays open beside your agent session. One glance answers
*where are we, what's next, what needs my eyes, is the machine healthy*:

- **Channel list + per-channel detail** — live workflow state, next action,
  and the full event log.
- **Unified review queue** — everything waiting on a human across niche
  opportunities, script examples, design exemplars, identity candidates, asset
  components, pilots, and episodes, each linking back to its evidence.
- **Wiki browsing** — channel memory as it accumulates.
- **One-click gated actions** — freezes, reviews, and GO/REVISE calls run as
  buttons, each shelling out to the exact same CLI with an explicit browser
  confirm first. The panel never re-implements tool logic and never fabricates
  an approval.

## Voice

Pilots and episodes are voice-first: `tools/voiceover.py synthesize` renders
narration fully offline (Piper TTS, voice model auto-downloaded on first use)
plus measured timing evidence, and `tools/voiceover.py validate` gates the
result against the target duration before any scene is built. One voice per
channel, picked once and reused.

## Rendering

Stage 9 (pilot production) doesn't assume a specific rendering pipeline — see
[`docs/RENDER_CONTRACT.md`](docs/RENDER_CONTRACT.md) for the evidence contract
any renderer must satisfy.

## Tools it stands on

One channel run touches every service below; the skill, the wiki, and the
control panel bind them into a single creator workflow. Nothing here phones
home — research and voice run on your machine or through your own setups.

| Tool | What it's used for here | Required? |
|---|---|---|
| [Hermes Agent](https://hermes-agent.nousresearch.com) | Public niche/market research: pulls competitor channel/video stats, opens breakout videos (screenshots included) for what-works teardowns. Raw numbers are shown to you before anything is imported. | Yes, for Stage 2 |
| Ollama + `ornith-1.5:9b` | Local model behind Hermes (~6.6GB one-time pull). Ollama automatically uses a supported NVIDIA, AMD, or Apple GPU when available; CPU remains supported. | Yes, for Stage 2 |
| Piper TTS (`lessac-medium`) | Channel voice: fully offline narration synthesis plus measured timing evidence every visual beat keys off. Model (~60MB) auto-downloads on first use. One voice per channel, picked once and enforced. | Yes, for pilot/episodes |
| Remotion (or any renderer) | Turns timed beats and components into the actual video file. Any pipeline works as long as it satisfies the evidence contract — Remotion is one valid choice, not a dependency. | Yes, for pilot/episodes |
| Obsidian | Human-readable learning memory: each channel folder *is* a vault (graph view works out of the box), and the style snapshot visibly accumulates lessons after every freeze and episode. | Optional, recommended |
| YouTube (public pages) | Evidence source only — public stats and captions the new channel learns *what's working* from, never to copy. Publishing the finished render stays manual, by you. | As a data source |
| Node/npm | Only needed if your channel's renderer is Remotion. | Only for Remotion |
| This repo's dashboard | Local-only (127.0.0.1) control panel: workflow progress, unified review queue, wiki browsing, confirm-gated freeze/review/GO buttons. | Optional, recommended |

## What's Inside

**Skill** — `.claude/skills/channel-maker/SKILL.md` plus setup and response-
contract references: the whole methodology above as an executable walkthrough.

**Engine** — `engine/` packages per lifecycle domain: channel state machine,
niche intelligence, foundation, script/design/identity DNA, asset library,
pilot, episodes, readiness checklist, scoped memory, and local voiceover.

**Tools** — `tools/` one CLI per domain plus `setup.py`, `check.py`, and the
`dashboard/` control panel that shells out to the same CLIs.

**Contracts & tests** — 40+ JSON schemas guarding every artifact, and a pytest
suite that executes the skill's documented path literally (including a resume
and a REVISE loop), so doc drift fails loudly.

## Philosophy

- **Evidence over claims** — verify with tool output before declaring success.
- **No AI approval** — scores, critics, and metrics advise; only a recorded
  human decision opens a gate.
- **Smallest reviewable step** — one stage, one freeze, one commit at a time.
- **Simplicity as primary goal** — CREATE-only v1, no speculative catalogs,
  no giant upfront systems.
- **Deterministic where practical** — content-hashed evidence, atomic writes,
  chained state history.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The headline rule: the skill-walkthrough
test executes the documented path, so skill changes come with test updates —
write the failing walkthrough first.

## Updating

```
git pull
python tools/setup.py
python tools/check.py
```

The voice model cache (`data/local/piper-voices/`) survives updates. Found a
security issue? See [SECURITY.md](SECURITY.md) — report privately, not via a
public issue.

## Verify

```
.venv/bin/python tools/check.py
```

Runs schema/channel/memory/niche-intelligence validation and the full pytest
suite.

## FAQ

**Do I need a GPU?**
No, but you will want one for speed. Ornith can run on CPU, while Ollama
can offload it to a supported NVIDIA, AMD, or Apple GPU. Claude asks you to
choose GPU (recommended) or CPU before it configures Hermes. For the 9B model
at the default 4096-token context, plan on at least 8 GB of **free** accelerator
memory; larger contexts and concurrent models need more.

```
python tools/ollama_gpu.py --processor gpu --require-full-gpu  # recommended
python tools/ollama_gpu.py --processor cpu                     # slower fallback
```

A hybrid result usually means another application is consuming accelerator
memory. Choose whether to close it, run `ollama stop ornith-1.5:9b`, and retry,
or explicitly accept the slower fallback. See
[Ollama's hardware support](https://docs.ollama.com/gpu).
Piper TTS and the rest of the Python tooling continue to work on CPU. Rendering
speed depends on whatever renderer your channel declares.

**What does it cost?**
Time, disk (~7GB for the local research model), and decisions. No API keys,
no subscriptions, nothing phones home.

**Isn't this just AI slop at scale?**
The workflow is built to resist exactly that: every freeze, review, and
GO/REVISE call requires a recorded human decision, enforced in code — scores
and metrics only advise. If you wave everything through, you'll get slop
faster. That's on you, and the gates make sure you know it.

**How long until my first channel is ready?**
Days of real decisions, not minutes. The pilot alone is a full
script → voice → visuals → render → review loop. Anyone promising faster is
selling a different thing.

**Built something with Channel Maker?**
Open a PR adding it to this section — show the channel, tell us what the
gates caught. Real examples beat every paragraph above.

## License

MIT — see [LICENSE](LICENSE).
