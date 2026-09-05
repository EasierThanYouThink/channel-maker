# Obsidian Wiki — the channel's learning memory

Every channel wiki (`channels/<id>/`) is a plain-Markdown **Obsidian vault**:
open the channel folder itself directly in Obsidian (Open folder as vault;
vault name = channel id, so every channel is its own vault). No plugins
required. Graph view works out of the box because pages link each other with
`[[wikilinks]]`. The control panel's vault card deep-links straight in via
`obsidian://open?vault=<channel_id>`.

## Layout (vault root = `channels/<id>/`)

```
channels/<id>/               # ← open THIS folder as the vault
  wiki/
    HOME.md                 # canonical entry point (memory index page)
  style/                  # DERIVED style snapshot — the AI's learned picture
    index.md              # links voice/visual/motion + lessons/failures
    voice.md              # how the channel sounds (from Script DNA)
    visual.md             # how the channel looks (from Visual DNA + logo)
    motion.md             # how the channel moves (from Motion DNA + lessons)
  market/observations|hypotheses|opportunities/
  script/ visual/ motion/ assets/
  decisions/ experiments/ lessons/ failures/
  videos/<video_id>/      # per-video memory (episode learnings land here)
```

Engine-level knowledge lives in `engine/memory/wiki/` (same frontmatter rules).

## The style-learning loop (the key idea)

Sources of truth are the frozen artifacts (`strategy/foundation.yaml`,
`script/script-dna.yaml`, `design/visual-dna-seed.yaml`,
`motion/motion-dna-seed.yaml`, `identity/channel-identity.yaml`). After every
freeze — and after every episode review — the agent re-runs:

```
python tools/channel_style.py sync channels/<id>
```

which rebuilds `wiki/style/*.md` (`ai_proposed` derivatives with `provenance`
back to the artifacts). The loop:

1. **Freeze** Script/Visual/Motion DNA or record an episode review.
2. **Sync** — style pages refresh (`--force` overwrites existing pages;
   without it only missing pages are written).
3. **Learn** — episode outcomes get a `lessons/` or `failures/` note; the next
   sync links them into `style/index.md` and `style/motion.md`, so the style
   visibly accumulates experience.
4. **Read** — humans browse the graph in Obsidian; agents query via
   `tools/channel_memory.py search|context` or `tools/channel_overview.py`
   (`style_pages` shows which snapshots exist).

Rules: never hand-edit a style page to change the channel — change the DNA
artifact, freeze with a real decision ref, re-sync. Style pages are
`ai_proposed`; promotion to canonical/human authority needs the governed human
path (same as all memory write-back). `tools/channel_style.py status` reports
page presence + approval counts without writing.

## Combining the services (why this repo exists)

One channel run touches every service; the wiki + control panel is what binds
them into a single creator workflow:

| Service | Role | Entry point |
|---|---|---|
| Hermes Agent | public niche/market research | Stage 2 queue (`submit/claim/complete`, `import-evidence`) |
| Ollama `ornith-1.5:9b` | local model behind Hermes | `docs/SETUP.md`, `tools/setup.py --check-only` |
| Piper TTS | channel voice, timing JSON | `tools/voiceover.py synthesize/validate` |
| Renderer (e.g. remotion) | scenes → render + eval evidence | `docs/RENDER_CONTRACT.md`, `build_scene_candidate.py`, `evaluate_scene.py` |
| YouTube (public) | evidence source; publishing stays manual | collection targets; skill Ongoing step 5 |
| Obsidian vault | human-readable learning memory | this doc, `tools/channel_style.py` |
| Control panel | ops status board from Stage 1.5 on | `tools/dashboard/server.py`, `tools/channel_overview.py` |

`tools/channel_overview.py <id>` proves the combination in one JSON: workflow
progress, review queue, style snapshot, pilots/episodes, and live service
health (`tools/_platform.py:service_status`).
