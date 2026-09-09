# Channel Maker — Claude builds your YouTube channel with you, then proves it

**Tell Claude your niche. It argues the thesis, researches competitors, locks voice & visuals, then ships a voice-first pilot. All locally, no API keys. You open every gate — enforced in code.**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](tools/setup.py)
[![Skill: channel-maker](https://img.shields.io/badge/skill-channel--maker-purple.svg)](.claude/skills/channel-maker/SKILL.md)

🎬 **Watch a pilot made with it** · 🚀 **Quickstart below (3 steps)** · 🛡️ **Local-only: Hermes + Ollama + Piper**

> Public beta — full path tested on Claude Code + Opus 5. Other harnesses experimental. Back up channel projects before upgrading.

<video src="https://github.com/user-attachments/assets/e0c09a15-ec66-4430-91aa-c5fdb87bacb5" controls width="640"></video>

*Above: pilot produced by the episode loop — script → offline TTS → measured timings → visual beats → render. Replace this caption with niche + runtime + voice when you publish yours.*

## Why this is different

Most AI video tools jump to script + render. This interrogates first.

It doesn't generate a logo. It asks why this channel, for whom, what every video promises — like a skeptical CEO — and only scaffolds when the thesis survives. Every freeze needs your recorded decision. Scores advise, you decide.

- **Human gates in code:** `freeze`, `review`, `GO/REVISE` only run with explicit approval. Dashboard buttons shell to the same CLI — never fabricates a gate.
- **Resume anywhere:** state lives in `CHANNEL_STATE.json`, not chat. Fresh session reconstructs and continues.
- **Voice-first:** `tools/voiceover.py synthesize` → `validate` gates duration before any scene is built.
- **Doc drift fails loudly:** 40+ JSON schemas + pytest that executes the skill path, including resume + REVISE.

If you wave everything through, you'll get slop faster. That's on you.

## Quickstart (Claude Code)

**You need:** ~7GB disk one-time (6.6GB local research model), no API keys, no cloud bill. GPU recommended for research speed, CPU works.

**1. Create a folder and open a terminal inside it:**
```bash
mkdir Claude_Channel && cd Claude_Channel
```

**2. Start Claude Code:**
```bash
claude
# Opus 5 on high effort gives best results
```

**3. Paste this:**
```
Clone https://github.com/EasierThanYouThink/channel-maker.git into this folder, then read .claude/skills/channel-maker/SKILL.md and README.md, run the full environment setup (venv, dependencies, service checks), and walk me through creating a YouTube channel in <your niche here> per the skill, starting at Stage 0.
```

**First success (<10 min, before big download finishes):** locked thesis + scaffolded Channel Package + `next` telling you what's legal.
**Full research:** needs Hermes Agent + `ornith-1.5:9b` pull (background, one-time). Claude will ask GPU or CPU during setup.

> Other agents: harness-agnostic by design (versioned contracts, file state, no lock-in), but only Claude Code has walked end-to-end. Codex / Gemini / local models on roadmap.

<details>
<summary>Per-OS setup & GPU choice</summary>

See [`docs/SETUP.md`](docs/SETUP.md). Quick GPU check:

```bash
python tools/ollama_gpu.py --processor gpu --require-full-gpu  # recommended
python tools/ollama_gpu.py --processor cpu                     # slower fallback
```

Need 8GB free accelerator memory for 9B model at 4k context. Piper TTS + Python tools run on CPU.
</details>

## What you get

After `CHANNEL_READY` you have:

- `CHANNEL_STATE.json` — resumable state + chained history
- Locked Script / Visual / Motion DNA + About bio in channel voice
- One offline voice (`Piper lessac-medium`, ~60MB) reused everywhere
- Pilot: script → timings JSON → beats → `mp4` + evaluation evidence
- Dashboard at `127.0.0.1:8420` — queue, wiki, gated buttons
- Obsidian-ready vault (optional) with lessons after every freeze

Example excerpt (illustrative — from your run it will differ):
```
HOOK: "I reviewed 47 videos in [niche]. Only 3 formats earn >2x median views."
BEAT 00:04-00:11 [VO 7.2s validated] → b-roll: teardown grid
NEXT: pilot GO/REVISE — only you can open
```

## How it works (3 phases)

**1. Argue** — intent + niche-intelligence + opportunity-map. Hermes pulls public stats/screenshots, you see raw numbers before import. Ends at strategy gate.
**2. Lock** — foundation → script-DNA → visual/motion-DNA → identity → starter-library. One freeze, one commit at a time.
**3. Produce** — pilot → readiness checklist (12 items) → episodes forever. Same rigor, no version bump.

<details>
<summary>Full 12-stage map (for evaluators)</summary>

- **resume** — reconstruct from `CHANNEL_STATE.json`, dry-run next edge
- **intent** — CEO-interrogate thesis, scaffold package
- **niche-intelligence** — Hermes research + teardowns + relative-views metric
- **opportunity-map** — options → human strategy gate
- **foundation** — audience, promise, boundaries, anti-list
- **script-dna** — hook philosophy, voice, density — frozen on sign-off
- **visual/motion-dna** — exemplars → narrowing loops → per-domain freezes
- **identity** — logo + About bio in channel voice
- **starter-library** — code-first components pilot needs, nothing speculative
- **pilot** — voice → timings → beats → render → GO/REVISE/ABANDON
- **readiness** — 12-item `CHANNEL_READY` checklist
- **episodes** — same rigor, no state-machine involvement
</details>

## Dashboard, Voice, Rendering

**Control panel:** `.venv/bin/python tools/dashboard/server.py --port 8420` — local-only. Channel list, unified review queue, wiki, one-click freezes/reviews with browser confirm.

**Voice:** `tools/voiceover.py synthesize` (offline Piper) + `validate` against target duration. One voice per channel, picked once.

**Rendering:** Bring any renderer that satisfies [`docs/RENDER_CONTRACT.md`](docs/RENDER_CONTRACT.md). Remotion is one valid choice, not a dependency. Publishing stays manual — by you.

## Local stack

| Tool | Used for | Required? |
|---|---|---|
| [Hermes Agent](https://hermes-agent.nousresearch.com) | Public research + teardowns. Raw numbers shown before import. | Yes, Stage 2 |
| Ollama + `ornith-1.5:9b` (~6.6GB) | Local model behind Hermes | Yes, Stage 2 |
| Piper TTS | Offline narration + timing evidence | Yes, pilot/episodes |
| Remotion or any renderer | mp4 from timed beats | Yes, pilot/episodes |
| Dashboard (this repo) | Progress + review queue + gated buttons | Recommended |
| Obsidian / Node / YouTube public pages | Vault view / Remotion only / evidence source | Optional / conditional |

Nothing phones home. Research + voice run on your machine.

## Why this instead of…

| Instead of… | They win on | This wins on |
|---|---|---|
| ChatGPT ideas/scripts | Speed, zero setup | Enforced steps, frozen style, resumable state |
| InVideo / Pictory / Opus | Templates, fast render, publish | Thesis pressure-test, human gates, local-only |
| Courses / playbooks | Proven taste | Executable system that blocks skipping |

Not claiming better renders. Claiming fewer skipped decisions.

## Verify

```bash
.venv/bin/python tools/check.py
git pull && python tools/setup.py && python tools/check.py
```

Runs schema/channel/memory validation + full pytest suite. Voice cache survives updates. Security: see [SECURITY.md](SECURITY.md).

## FAQ

**Do I need a GPU?** No, but want one for Ornith speed. See per-OS setup above.

**What does it cost?** Time, disk, decisions. No keys, no subs.

**Isn't this slop at scale?** Built to resist it: every freeze/review/GO needs recorded human decision. Wave it through → slop faster. Gates make sure you know it.

**How long to first channel?** Days of real decisions, not minutes. Pilot alone is script → voice → visuals → render → review.

**Built something?** Open a PR with channel + what gates caught. First 3 featured here. Real examples beat paragraphs.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Rule: skill-walkthrough test executes documented path — change skill, update test. Write failing walkthrough first.

## License

MIT — see [LICENSE](LICENSE).
