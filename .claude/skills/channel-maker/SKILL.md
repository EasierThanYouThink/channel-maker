---
name: channel-maker
description: Create a new YouTube channel (niche-driven, CREATE-only in v1), using Hermes Agent for public market research, and walk it through this repo's full CM1 workflow from CHANNEL_INIT to CHANNEL_READY — niche intelligence, channel foundation, Script/Visual/Motion DNA discovery, channel identity, the starter asset library, and pilot production/review/freeze — then keep producing ongoing episodes, plus a local dashboard and Obsidian vault. Use when the user wants to start a new YouTube channel, research a niche, set up Hermes Agent for channel market research, or produce another episode for an already-ready channel.
---

# Channel Maker (v1 — Claude Code only)

This skill walks a Channel Package through its entire CM1 lifecycle: interactive
environment bootstrap, channel intent, Hermes-driven niche/market research,
channel foundation, Script/Visual/Motion DNA discovery (see
`docs/CHANNEL_DESIGN_DNA.md`), channel identity — logo + description (see
`docs/CHANNEL_IDENTITY.md`), the starter asset library, and pilot
planning/production/review/freeze, ending at `CHANNEL_READY` — followed by an
ongoing, repeatable Episode Production loop for the channel's actual videos.
See `README.md` first if you have not already reconstructed current
repository state this session.

Creative scene construction itself (Stage 9) is a bounded, human/agent-driven
workflow using whatever rendering pipeline the channel declares (see
`docs/RENDER_CONTRACT.md`) — this skill does not invent a Scene DSL or an
automatic "visual director." What's new is the lifecycle/contract layer around
each stage: every domain freeze, example/exemplar/component review, and pilot
decision requires a real, non-fabricated human confirmation and decision
reference, enforced in code, not just by convention.

Everything here is a live, conversational walkthrough — use Bash, AskUserQuestion,
and normal multi-turn conversation as needed at every step. Nothing in this
skill fabricates a human decision, a reviewer name, or an approval on the
user's behalf; every gate below requires the user's real input.

## Stage 0 — Interactive Bootstrap

Full checklist: [references/hermes-setup.md](references/hermes-setup.md). Summary:

1. Run the machine check first — it reports venv, Python, and every external
   service (Hermes, Ollama, Piper, Node) as JSON for you to parse:
   `python tools/setup.py --check-only --json` (human-readable without
   `--json`). Act on every `MISS` below before continuing.
2. Hermes MISS: tell the user to install Hermes Agent from
   hermes-agent.nousresearch.com and stop here — do not guess an install
   command. Hermes OK: **hard requirement** — run `hermes --help`,
   `hermes skills --help`, `hermes config --help` to discover the real CLI
   surface before running any task command. Do not guess flags.
3. Ollama MISS: tell the user to install it from ollama.com. Ollama OK but
   `ornith-1.5` absent from `ollama list` (grep/`Select-String` per OS):
   confirm with the user, then `ollama pull ornith-1.5:9b` (~6.6GB).
4. Configure `~/.hermes/config.yaml` (`%USERPROFILE%\.hermes\config.yaml` on
   Windows) so Hermes uses the local model, using whatever syntax step 2
   discovered (a `providers.custom` block pointing `base_url` at
   `http://localhost:11434/v1` with `model: "custom/ornith-1.5:9b"` is the
   expected shape, but confirm against the real CLI/config help rather than
   assuming).
5. Interactively install whatever Hermes skills cover web search, YouTube data, and screenshots — confirm each prompt with the user rather than silently accepting defaults.
6. **Go/no-go smoke test:** have Hermes fetch one public YouTube channel page and confirm it returns something sensible. If Hermes has no clean one-shot "run task, get structured output" mode, tell the user and fall back to collecting directly via WebFetch/WebSearch in Stage 2, using Hermes only for whatever it's confirmed to do well.

Do not proceed to Stage 1 until step 6 succeeds or the user explicitly accepts the WebFetch/WebSearch fallback. Re-run the step-1 check at the start of every session — services break between sessions; the check takes one second.

## Stage 0.5 — Resume (every session starts here)

A fresh session never assumes it starts at the beginning. Before doing anything else:

1. `.venv/bin/python tools/channel_state.py show channels/<channel_id>` — full identity + workflow state dump.
2. `.venv/bin/python tools/channel_state.py next channels/<channel_id>` — the machine's own answer for what's legal now: `allowed_operations`, the single `forward_state`, whether prerequisite refs or a human decision are required, and the recorded `next_action`. **This output, not the stage list below, decides your next command.** If it says `BLOCKED_ON_HUMAN`, your only legal operations are `resume` and `abandon` (see step 5) — `advance` will fail.
3. Unsure an edge is legal? Dry-run it first: `.venv/bin/python tools/channel_state.py validate-transition channels/<channel_id> <TARGET> --prerequisite-ref ... [--human-decision-ref ...]` checks legality and path existence without bumping `revision`.
4. Never re-run a scaffold step blindly — most constructors refuse duplicates (`init_channel`, `init_niche_study`, `design_dna init`, `channel_identity init`, `pilot/episode plan` all fail if the artifact exists). If the artifact already exists, skip to the step that consumes it. Conversely, never re-run a `write` (foundation, Script DNA) to "fix" a draft after decisions were attached or frozen: re-writing wipes `decision_refs` and frozen flags. If a re-write or re-freeze is refused, read the error — it tells you whether `--force` is the deliberate escape hatch or you are repeating finished work.
5. If the user needs to pause for a human (or the channel is already blocked): `.venv/bin/python tools/channel_state.py block channels/<channel_id> --actor "<user>" --reason "..." --reason-code <code> --summary "..." --question "..." --required-action "..."`, then later `.venv/bin/python tools/channel_state.py resume channels/<channel_id> --actor "<user>" --reason "..." --human-response-ref <a-real-path> --next-action "..."`. While blocked, only `resume` is legal.

## Stage 1 — Intent + Channel Scaffold

If `channels/<channel_id>` already exists (Stage 0.5), skip the scaffold and continue from the machine's `next` output — do not re-run `init_channel`, which refuses duplicates.

1. Ask the user for the new channel's intent: what niche, who it's for, what
   promise it makes. (Studying/cloning an existing channel returns in v2 —
   v1 is CREATE-only, niche-driven.)
2. Collect: `channel_id` (lowercase, e.g. `my-science-shorts`), display name, primary niche, archetype (`ILLUSTRATED_EXPLAINER` / `DATA_STORY` / `MAP_STORY`), language (default `en`), formats (default `SHORTS`), and the renderer this channel's pilots will use (e.g. `remotion` — see `docs/RENDER_CONTRACT.md`; any name is valid as long as Stage 9's evidence matches the contract).
3. **CEO interrogation — ask a lot, accept little.** Before scaffolding, put
   the user through the hard questions, one or two per turn so it stays a
   conversation, not a form:
   - Why should anyone watch this channel instead of the 3 competitors from
     Stage 2 (or the biggest channels in the niche if none named yet)?
   - What exactly is this channel better at than them — name the thing, not
     the vibe?
   - Who is it for, specifically — what does that person get in 25 seconds
     that they can't get elsewhere?
   - What promise does *every single video* keep?
   - Why will the 10th video still be worth making — what's the inexhaustible
     core?
   - What would make *you* subscribe after one video?
   **Push-back rule:** vague answers ("good content", "everyone", "it'll be
   entertaining", "high quality") are not answers — say so plainly, explain
   what's missing, and discuss until the reasoning is concrete enough to
   differentiate the channel on paper. If the user's reasoning is weak, argue
   with it: steelman the competitor, attack the thesis, and only move on when
   the thesis survives. Never fabricate confidence the user didn't earn.
4. Run the scaffold first (the package directory must not exist yet — do not
   create any files under `channels/<channel_id>/` beforehand):
   ```
   .venv/bin/python tools/init_channel.py <channel_id> --name "<name>" --niche-primary "<niche>" \
     --archetype <ARCHETYPE> --renderer <renderer>
   ```
5. Write the surviving answers down as the channel thesis:
   `channels/<channel_id>/strategy/channel-thesis.md` (thesis, named audience,
   the differentiator in one sentence, the every-video promise). This file
   becomes the `human_decision_ref` the strategy gate in Stage 3 points at.
6. `.venv/bin/python tools/validate_channel.py channels/<channel_id>` to confirm.
7. `.venv/bin/python tools/channel_state.py advance channels/<channel_id> NICHE_INTELLIGENCE --next-action "Run Hermes-driven niche research." --actor "<user or 'claude'>" --reason "Channel initialized."

## Stage 1.5 — Channel Control Panel (start it, open it, keep it open)

Right after the scaffold (or right after Resume if the channel already exists),
Claude **starts and opens** the channel's control panel and keeps it open for
the whole lifecycle. The panel shell is prebuilt (see "Starting the dashboard"
below) — nothing is coded in-session; the per-channel contents fill in live as
stages complete. It is the creator dashboard — one glance answers "where are
we, what's next, what needs my eyes, is the machine healthy".

1. Start it: `python tools/dashboard/server.py --port 8420` (local-only
   `127.0.0.1`; Windows: venv activated via `.venv\Scripts\Activate.ps1`).
   Open `http://127.0.0.1:8420/overview/<channel_id>`.
2. Snapshot the same data in chat (the panel and this CLI read the same
   source — `tools/dashboard/views.py:channel_overview`):
   `python tools/channel_overview.py <channel_id>`.
3. What's visible (fixed creator-dashboard layout, same order in UI + CLI):
   1. **Header** — name, niche, archetype, renderer, version, state badge,
      step `N/15`.
   2. **Workflow progress** — all 15 states with done/current/todo.
   3. **Next action** — `next_action` text + allowed operations + whether a
      human decision is required. This, not memory, decides the next command.
   4. **Review queue (this channel)** — counts of pending script examples,
      design exemplars, identity candidates, asset components, undecided
      pilots/episodes, proposed opportunities.
   5. **Obsidian vault** — vault path + "Open in Obsidian" button, style pages
      (`voice`/`visual`/`motion`/`index`), and the latest wiki notes with
      excerpts (see Stage 1.6).
   6. **Pilots & episodes** — each id + decision + frozen flag.
   7. **Services health** — Hermes / Ollama / Piper / Node presence
      (`tools/_platform.py:service_status`; MISS is fine, just say so).
   8. **Recent events** — last 10 state transitions with actor + reason.
   9. **Wiki shortcuts** — HOME, style index, market, decisions.
4. Revisit the panel at every stage boundary (it updates itself — it only
   reads files). If the panel and `channel_state.py next` ever disagree, `next`
   wins and the panel has a bug — report it.

## Stage 1.6 — Obsidian Vault (memory the human can see)

The channel memory is a real Obsidian vault, not just agent context — the
human browses the same learning memory in Obsidian's graph that the agent
queries via `tools/channel_memory.py`. Set it up once, then feed it every
stage (see `docs/OBSIDIAN_WIKI.md`).

1. Check for Obsidian: `which obsidian` (macOS/Linux) or
   `where obsidian` (Windows PowerShell). If missing, tell the user to install
   it from obsidian.md — the vault works fully after install, and the skill
   continues with the in-panel wiki preview meanwhile.
2. The vault root is `channels/<channel_id>/` (vault name = channel id, so
   every channel is its own vault). Create the memory skeleton if Stage 1 did
   not already: `python tools/channel_memory.py init channels/<channel_id>`.
3. Seed the style snapshot immediately, even pre-freeze (placeholders are
   expected at step 1/15): `python tools/channel_style.py sync
   channels/<channel_id>`. Confirm with `python tools/channel_style.py status
   channels/<channel_id>`.
4. Tell the user to open `channels/<channel_id>/` as a vault in Obsidian
   (Open folder as vault), or click **Open in Obsidian** on the control panel
   (`/overview/<channel_id>`), which deep-links via
   `obsidian://open?vault=<channel_id>`.
5. From here on, every freeze and every episode review ends with: write the
   `lessons/` (or `failures/`) note, then `python tools/channel_style.py sync
   channels/<channel_id> --force`. Both Obsidian and the control panel's vault
   card update themselves — verify by glancing at the panel.

## Stage 2 — Hermes-Driven Niche Intelligence

1. Scaffold the study:
   ```
   .venv/bin/python tools/init_niche_study.py channels/<channel_id> --study-id <study-id> \
     --niche "<niche>" --archetype <ARCHETYPE> --format SHORTS --language en \
     --channel-role GROWTH_CANDIDATE --channel-role BASELINE_COMPARATOR \
     --video-role BREAKOUT --video-role CHANNEL_BASELINE \
     --window-from <ISO8601> --window-to <ISO8601>
   ```
2. Build the collection request describing what to go collect (niche keywords — v1 is CREATE-only).
   Ask the user for up to 3 competitor channels doing well in this niche (public
   URLs or @handles) — Hermes pulls their public statistics so the new channel
   learns **what is working** (formats, pacing, topics, upload rhythm), never to
   copy expression. Pass each with a repeatable `--reference-channel`:
   ```
   .venv/bin/python tools/build_niche_collection_request.py \
     --channel-id <channel_id> --study-id <study-id> --target "<niche keywords>" \
     [--reference-channel "https://www.youtube.com/@somechannel" ...] \
     --allowed-channel-role GROWTH_CANDIDATE --allowed-channel-role BASELINE_COMPARATOR \
     --allowed-video-role BREAKOUT --allowed-video-role CHANNEL_BASELINE \
     --output data/local/hermes-queue/requests/<slug>.json
   ```
   Competitors enter the study as `BASELINE_COMPARATOR` channels: calibration
   only. Their scripts, thumbnails, and hooks are never reproduced — if a
   Script DNA example is ever adapted from observed evidence, it must use
   `--provenance-kind adapted_from_evidence` with the real `--source-ref`.
3. `.venv/bin/python tools/submit_hermes_job.py data/local/hermes-queue/requests/<slug>.json`
4. `.venv/bin/python tools/run_hermes_job_queue.py claim --next` — note the printed `response_path`/`runtime_metadata_path`. If there is no pending job it fails: re-check what you submitted. If collection itself fails, record that honestly with `.venv/bin/python tools/run_hermes_job_queue.py fail <job_id> --error "..."` rather than completing with invented data.
5. Drive Hermes live (per the CLI surface discovered in Stage 0) to collect public channel/video stats for the target. **Never record private analytics** (CTR, retention, swipe-away rate, average % viewed, traffic sources, subscriber conversion) — leave a field `null` if only a private version is available.
6. Write the response and runtime-metadata files yourself in the exact shape documented in [references/evidence-response-contract.md](references/evidence-response-contract.md).
7. `.venv/bin/python tools/run_hermes_job_queue.py complete <job_id>`.
8. **Show the user the raw collected numbers before importing — this is the real manual-review moment**, not a formality.
9. `.venv/bin/python tools/niche_intelligence.py import-evidence channels/<channel_id>/intelligence/studies/<study-id> <response_path> --reviewed-by "<the user's real name>"`. This fails loudly if `--reviewed-by` is empty — never fabricate a name.
10. Optionally, for a flagged breakout video: `.venv/bin/python tools/niche_intelligence.py relative-views <request.json>`.
11. **What-works teardown — watch the winners, write down how they work.** For
    each BREAKOUT video and each reference-channel video worth learning from,
    have Hermes actually open it (screenshots included where Hermes does them
    well) and record three structured teardowns as annotation artifacts. Write
    each payload to a JSON file first (fields per the schemas in
    `engine/niche_intelligence/contracts/` — use `UNKNOWN`/`null` honestly
    where Hermes can't see), then:
    ```
    .venv/bin/python tools/niche_intelligence.py add-teardown-content channels/<channel_id>/intelligence/studies/<study-id> \
      --key <video-slug> --video-evidence-id <niche:video:...> --payload-json <content-payload>.json --confidence 0.6

    .venv/bin/python tools/niche_intelligence.py add-teardown-script channels/<channel_id>/intelligence/studies/<study-id> \
      --key <video-slug>-script --video-evidence-id <niche:video:...> --payload-json <script-payload>.json --confidence 0.6

    .venv/bin/python tools/niche_intelligence.py add-teardown-visual channels/<channel_id>/intelligence/studies/<study-id> \
      --key <video-slug>-visual --video-evidence-id <niche:video:...> --payload-json <visual-payload>.json --confidence 0.6
    ```
    Content teardown captures hook family + hook text, structure, viewer
    promise, density/depth/novelty, ending. Script teardown captures
    transcript provenance (public captions only — never rip protected
    expression), word count, WPS, opening excerpt, question/numeric counts,
    hook/structure/ending judgments. Visual teardown captures production
    approaches, pacing/text-density proxies, metaphor usage, continuity — and
    stays `MARKET_EVIDENCE` with `design_authority: PROHIBITED`: it may inform
    taste, never dictate design or enter the renderer.
12. Synthesize the interpretive chain from the imported evidence (a real opportunity map cannot come from raw evidence alone). Start from the competitor statistics and the teardowns: for each reference channel, write at least one observation about what is working there (format/pacing/topic pattern with `--basis PUBLIC_FACT` and the competitor's evidence ref; use `--basis ANNOTATION` with the teardown ref for how-it-works claims), then hypotheses about *why* it works, then opportunities for the new channel to do the un-served variant:
    ```
    .venv/bin/python tools/niche_intelligence.py add-observation channels/<channel_id>/intelligence/studies/<study-id> \
      --key <slug> --statement "..." --observation-type PERFORMANCE_PATTERN --scope "..." --basis PUBLIC_FACT \
      --evidence-ref <video-or-channel-evidence-artifact-id> --confidence 0.7 --limitation "..."

    .venv/bin/python tools/niche_intelligence.py add-hypothesis channels/<channel_id>/intelligence/studies/<study-id> \
      --key <slug> --statement "..." --predicted-effect "..." --applicable-context "..." \
      --observation-ref <observation-artifact-id> --competing-explanation "..." --confidence 0.5

    .venv/bin/python tools/niche_intelligence.py add-opportunity channels/<channel_id>/intelligence/studies/<study-id> \
      --key <slug> --observed-market "..." --underrepresented "..." --proposal "..." \
      --hypothesis-ref <hypothesis-artifact-id> --evidence-ref <observation-artifact-id> --risk "..." --confidence 0.4
    ```
12. `.venv/bin/python tools/niche_intelligence.py validate channels/<channel_id>/intelligence/studies/<study-id>` must pass before Stage 3. `publish-summaries` (Stage 3) carries teardowns into `wiki/market/teardowns/` alongside the stats, so the wiki remembers *how* the winners work, not just their numbers.

Sample-role assignment (`GROWTH_CANDIDATE`, `BREAKOUT`, etc.) is a judgment call — there is no deterministic threshold in this repo's philosophy (`docs/NICHE_INTELLIGENCE.md`). Use your own analysis and say so plainly.

## Stage 3 — Opportunity Map + Human Gate

1. `.venv/bin/python tools/niche_intelligence.py publish-summaries channels/<channel_id> channels/<channel_id>/intelligence/studies/<study-id>`.
2. Summarize the opportunity map for the user conversationally from those wiki pages / the `opportunity_proposal` artifacts.
3. Advance through the map state first (prerequisite evidence only — no human gate on this edge):
   ```
   .venv/bin/python tools/channel_state.py advance channels/<channel_id> OPPORTUNITY_MAP --next-action "Select a channel strategy." --actor "<user>" --reason "<reason>" --prerequisite-ref <path-to-opportunity-map-evidence>
   ```
4. Get the user's real strategy decision — and stress-test it first. Put the
   Stage 1 thesis (`channels/<channel_id>/strategy/channel-thesis.md`) next to
   the competitor statistics and attack it: does the evidence support the
   differentiator, or does some competitor already own it? Ask the killer
   question out loud ("your thesis says X, but competitor Y's numbers show Z —
   defend or revise"). Same push-back rule as Stage 1: weak reasoning gets
   discussed, not waved through. Write the surviving decision down first as a structured record (selected opportunity ids, the rejected alternative, the resource constraint, and the revisit condition) — a
   `tools/decision_record.py write channels/<channel_id>/strategy/strategy.md --kind strategy --title "<title>" --summary "<why this direction>" --selected <opportunity-id> [--selected ...] --rejected <declined-alternative> [--constraint "<budget>"] --revisit "<when to reconsider>" --author "<user>" (a plain markdown note also works, but records the decision less precisely) — because `human_decision_ref` must resolve to a real repository file, never a fabricated string. Then cross the workflow's first human gate:
   ```
   .venv/bin/python tools/channel_state.py advance channels/<channel_id> STRATEGY_SELECTION --next-action "<next action>" --actor "<user>" --reason "<reason>" --prerequisite-ref <path-to-opportunity-map-evidence> --human-decision-ref <the-real-reference>
   ```
5. `.venv/bin/python tools/validate_channel.py channels/<channel_id>` as a final check.

## Stage 4 — Channel Foundation

1. Draft the conceptual identity layer with the user (audience, promise, personality, differentiation, emotional goal, boundaries, what the channel deliberately avoids). Hold it against the channel thesis from Stage 1 — if the foundation drifts from the thesis, say so and resolve the contradiction before writing:
   ```
   .venv/bin/python tools/channel_foundation.py write channels/<channel_id> \
     --audience-description "..." --promise "..." --niche-primary "<niche>" \
     --personality <trait> [--personality <trait> ...] --balance <MOSTLY_EDUCATIONAL|BALANCED|MOSTLY_ENTERTAINMENT> \
     --differentiation "..." --emotional-goal "..." --content-boundary "..." \
     --primary-format SHORTS --avoids "..."
   ```
2. Get the user's real sign-off, write the decision note first (same create-file-first rule as Stage 3), and attach it: `.venv/bin/python tools/channel_foundation.py attach-decision channels/<channel_id> --decision-ref <a-real-path>`. Verify with `.venv/bin/python tools/channel_foundation.py validate channels/<channel_id>`.
3. `.venv/bin/python tools/channel_state.py advance channels/<channel_id> CHANNEL_FOUNDATION --next-action "..." --actor "<user>" --reason "..." --prerequisite-ref channels/<channel_id>/strategy/foundation.yaml`.

## Stage 5 — Script DNA Discovery

1. Draft candidate scripting identity: `.venv/bin/python tools/script_dna.py write channels/<channel_id> --hook-philosophy "..." --narrator-personality <trait> ... --sentence-length-qualitative "..." --technical-depth "..." --humor-level "..." --information-density "..." --question-usage "..." --number-usage "..." --story-structure "..." --ending-behavior "..." --cta-philosophy "..." --fact-verification-requirements "..."` (add `--preferred-cliche`/`--forbidden-cliche`/`--unresolved-variable` as needed).
2. Prove it with examples — at least one approved example is required before any freeze (collect rejected alternatives too; they record the voice's boundary): `tools/script_dna.py add-example channels/<channel_id> --text "..." --provenance-kind <human_authored|model_drafted|adapted_from_evidence> --created-by "<you>" --source-ref "..."`, then `tools/script_dna.py review-example channels/<channel_id> <example_id> --decision <approved|rejected|borderline> --reviewer "<user>" --reason "..."` (interactive confirm, or `--yes` if already confirmed with the user in chat).
3. Audition the voice before freezing: synthesize the approved example (`tools/voiceover.py synthesize` with the channel's candidate voice), play it to the user, and get their listen-check sign-off — never freeze adjectives the user hasn't heard. Then freeze — decision note first, then: `.venv/bin/python tools/script_dna.py freeze channels/<channel_id> --decision-ref <a-real-path> --audition-example <example_id> --audition-timing <timing-json>` (interactive confirm, or `--yes`). Verify with `.venv/bin/python tools/script_dna.py validate channels/<channel_id>`. Then update the learning memory: `python tools/channel_style.py sync channels/<channel_id> --force` (refreshes `wiki/style/voice.md`; see `docs/OBSIDIAN_WIKI.md`).
4. `.venv/bin/python tools/channel_state.py advance channels/<channel_id> SCRIPT_DNA_DISCOVERY --next-action "..." --actor "<user>" --reason "..." --prerequisite-ref channels/<channel_id>/script/script-dna.yaml`.

## Stage 6 — Visual + Motion DNA Discovery

Visual DNA has five domains (`visual_identity`, `typography`, `color_language`, `composition_grammar`, `scene_aesthetics`); Motion DNA has one (`motion_identity`) — separate artifacts, per `docs/CHANNEL_DESIGN_DNA.md`. For each:

1. `.venv/bin/python tools/design_dna.py <visual|motion> init channels/<channel_id>`.
2. Discovery loop per domain: create/gather candidate reference images, register them (`tools/design_exemplars.py --channel <channel_id> add <image> --title "..." --domain <domain> --provenance-kind <...> --created-by "<you>" --source-ref "..."`), show the user, get their approve/reject/borderline call (`tools/design_exemplars.py --channel <channel_id> review <exemplar_id> --decision ... --reviewer "<user>" --reason "..."`, interactive confirm or `--yes` if already confirmed in chat), then `tools/design_dna.py <visual|motion> add-reference channels/<channel_id> --domain <domain> --exemplar-id <exemplar_id>` for approved ones. Narrow and repeat until the user is satisfied — do not invent a fixed number of rounds. Before freezing, compose one frame showing the domains together and show it to the user: individually attractive references can clash as a system.
3. Freeze each domain only when the user explicitly says so (a domain with no approved references cannot freeze) — decision note first, then: `tools/design_dna.py <visual|motion> freeze-domain channels/<channel_id> --domain <domain> --decision-ref <a-real-path>` (interactive confirm, or `--yes`). Re-freezing an already-frozen domain is refused unless you pass `--force` — treat that refusal as a signal you are repeating work, not as an error to route around. After each freeze: `python tools/channel_style.py sync channels/<channel_id> --force` (refreshes `wiki/style/visual.md` / `motion.md`).
4. `tools/design_dna.py <visual|motion> check-ready channels/<channel_id>` must report all domains frozen before advancing (`tools/design_dna.py <visual|motion> validate channels/<channel_id>` is the schema-level check).
5. Walk the three edges in order, each with `--next-action`, `--actor`, `--reason`, and `--prerequisite-ref`:
   - `... advance channels/<channel_id> VISUAL_DNA_DISCOVERY ... --prerequisite-ref channels/<channel_id>/script/script-dna.yaml` once Script DNA is frozen;
   - `... advance channels/<channel_id> MOTION_DNA_DISCOVERY ... --prerequisite-ref channels/<channel_id>/design/visual-dna-seed.yaml` after visual is fully frozen;
   - `... advance channels/<channel_id> CHANNEL_IDENTITY ... --prerequisite-ref channels/<channel_id>/motion/motion-dna-seed.yaml` after motion is fully frozen.

## Stage 7 — Channel Identity

Only starts once Foundation, Script DNA, and Visual DNA are frozen — see
`docs/CHANNEL_IDENTITY.md`. Two domains: `logo` (an image) and `description` (a
short About-page bio, in the frozen Script DNA voice).

1. `.venv/bin/python tools/channel_identity.py init channels/<channel_id>`.
2. Discovery loop per domain: produce/gather candidates (a logo image, or a draft description string), register them (`tools/channel_identity.py add --channel <channel_id> --domain <logo|description> --title "..." [--image <path> | --text "..."] --provenance-kind <...> --created-by "<you>" --source-ref "..."`), show the user, get their approve/reject/borderline call (`tools/channel_identity.py review --channel <channel_id> <candidate_id> --decision ... --reviewer "<user>" --reason "..."`, interactive confirm or `--yes` if already confirmed in chat), then `tools/channel_identity.py add-reference channels/<channel_id> --domain <domain> --candidate-id <candidate_id>` for approved ones. Narrow and repeat until the user is satisfied — do not invent a fixed number of rounds. Attach exactly the selected candidate per domain (the deliverable, not the shortlist) and show the logo at actual avatar size.
3. Freeze each domain only when the user explicitly says so (a domain with no references cannot freeze) — decision note first, then: `tools/channel_identity.py freeze-domain channels/<channel_id> --domain <domain> --decision-ref <a-real-path>` (interactive confirm, or `--yes`). Same `--force` rule as Stage 6 for re-freezes. Then `python tools/channel_style.py sync channels/<channel_id> --force`.
4. `tools/channel_identity.py check-ready channels/<channel_id>` must report both domains frozen before advancing (`tools/channel_identity.py validate channels/<channel_id>` is the schema-level check).
5. `.venv/bin/python tools/channel_state.py advance channels/<channel_id> STARTER_VISUAL_LIBRARY --next-action "..." --actor "<user>" --reason "..." --prerequisite-ref channels/<channel_id>/identity/channel-identity.yaml`.

## Stage 8 — Starter Visual Library

Only create a component when a real, immediate need exists (never a speculative catalog):

1. `.venv/bin/python tools/asset_registry.py register --scope CHANNEL --channel-id <channel_id> --category <primitive|object|character|diagram|mechanism|effect> --name "..." --description "..." --renderer <renderer> --source-kind tsx --source-path <renderer>/src/channels/<channel_id>/<Name>.tsx --export <ExportName> --justification "..."` after actually writing the component.
2. Get the user's review against a rendered scene using the component — never approve source code the user hasn't seen working: `tools/asset_registry.py review <component_path> --decision <approved|rejected|deprecated> --reviewer "<user>" --reason "..."` (interactive confirm, or `--yes` if already confirmed in chat). The review binds the verdict to the source bytes. A rejection is terminal: the component leaves the queue for good.
3. `.venv/bin/python tools/channel_state.py advance channels/<channel_id> PILOT_PLAN --next-action "..." --actor "<user>" --reason "..." --prerequisite-ref <approved-component-path>` once at least one component is approved. If the pilot honestly needs no reusable component (scene-local construction), skip the library instead of registering a token part: pass `--no-reusable-components` to `tools/pilot.py plan`.

## Stage 9 — Pilot Plan, Production, Review

1. `.venv/bin/python tools/pilot.py plan channels/<channel_id> <pilot-id> --topic "..." --target-duration-seconds <20-30> --integration-goal "Prove Script DNA" --integration-goal "Prove Visual DNA" ...`, then advance into production with the pilot plan as prerequisite evidence:
   ```
   .venv/bin/python tools/channel_state.py advance channels/<channel_id> PILOT_PRODUCTION --next-action "..." --actor "<user>" --reason "..." --prerequisite-ref channels/<channel_id>/pilots/<pilot-id>/pilot.json
   ```
   (Stage 8's advance already moved the channel to `PILOT_PLAN`; this edge moves it to `PILOT_PRODUCTION`.)
2. Build the pilot with the channel's declared renderer — script, voiceover, timed visual beats, scene-local components, a deterministic render — per the contract in `docs/RENDER_CONTRACT.md`, using the evaluation contract tooling for evidence. Voice first, because everything visual keys off it:
   1. Write the final script to a file (e.g. `channels/<channel_id>/pilots/<pilot-id>/script.md`) and fact-check it against the Script DNA requirements.
   2. Synthesize the narration — one voice per channel, picked now and reused forever after:
      ```
      .venv/bin/python tools/voiceover.py synthesize --script-path channels/<channel_id>/pilots/<pilot-id>/script.md --voice lessac-medium \
        --output-audio channels/<channel_id>/pilots/<pilot-id>/voiceover.wav \
        --output-timing channels/<channel_id>/pilots/<pilot-id>/voiceover-timing.json
      ```
      The first run downloads the voice model (~60MB) into `data/local/piper-voices/`; synthesis itself is fully offline.
   3. Play it back to the user (or report duration + sentence/word counts) and get their sign-off on the read. If they want line changes, edit the script and re-synthesize — never hand-edit the timing JSON.
   4. `.venv/bin/python tools/voiceover.py validate channels/<channel_id>/pilots/<pilot-id>/voiceover-timing.json --target-duration-seconds <20-30>` must pass — this proves the narration fits the format before any scene is built.
   5. Derive timed visual beats from the timing JSON's sentence spans, build scenes, and package evidence: `.venv/bin/python tools/build_scene_candidate.py --scene-id ... --generator-agent ... --model ... --prompt-version ... --input audio=channels/<channel_id>/pilots/<pilot-id>/voiceover.wav --input narration_timing=channels/<channel_id>/pilots/<pilot-id>/voiceover-timing.json ... --output <manifest-path>`, then `.venv/bin/python tools/evaluate_scene.py ...` per its `--help`.
   6. Attach everything as it's produced (repeat `record-production` as new evidence lands — it dedups by artifact id):
      ```
      .venv/bin/python tools/pilot.py record-production channels/<channel_id> <pilot-id> --script-ref channels/<channel_id>/pilots/<pilot-id>/script.md --voiceover-ref channels/<channel_id>/pilots/<pilot-id>/voiceover.wav --scene-candidate-manifest <path> --evaluation-result <path> --render-ref ...
      ```
   7. `.venv/bin/python tools/pilot.py validate channels/<channel_id> <pilot-id>` as a final evidence check.
3. `.venv/bin/python tools/channel_state.py advance channels/<channel_id> PILOT_REVIEW --next-action "..." --actor "<user>" --reason "..." --prerequisite-ref channels/<channel_id>/pilots/<pilot-id>/pilot.json`.
4. Get the user's real GO/REVISE/ABANDON_DIRECTION decision — never fabricate it. Write the decision record first (same create-file-first rule as Stage 3): read the production rev from `channels/<channel_id>/pilots/<pilot-id>/pilot.json` (`production.revision`), then `tools/decision_record.py write channels/<channel_id>/pilots/<pilot-id>/review-<decision-lower>.md --kind review --title "<title>" --summary "<rationale>" --decision <GO|REVISE|ABANDON_DIRECTION> --rev <production-rev> --author "<user>" — the record binds the verdict to the exact production bytes it approves, then:
   ```
   .venv/bin/python tools/pilot.py record-review channels/<channel_id> <pilot-id> --decision GO --decided-by "<user>" --decision-ref <a-real-path> --rationale "..." --yes
   ```
   (`--yes` is required non-interactively; without it the CLI stops and asks. Re-recording a review archives the previous decision into the review history — check the current one first.)
   REVISE requires `--revise-target <STATE>` where `<STATE>` is one of the fixed re-entry states (`STRATEGY_SELECTION`, `CHANNEL_FOUNDATION`, `SCRIPT_DNA_DISCOVERY`, `VISUAL_DNA_DISCOVERY`, `MOTION_DNA_DISCOVERY`, `CHANNEL_IDENTITY`, `STARTER_VISUAL_LIBRARY`, `PILOT_PLAN`, `PILOT_PRODUCTION` — niche-intelligence states and `PILOT_REVIEW` itself are not valid targets) and routes via `tools/channel_state.py revise channels/<channel_id> <STATE> --actor "<user>" --decision-ref <same-ref> --next-action "..." --reason "..." --yes`. A revise truncates `completed` at the target and sets status `REVISING`: re-walk forward with fresh `advance` calls (each needing its own prerequisite refs) until `PILOT_REVIEW`, then record the new review. Frozen DNA/identity artifacts are not auto-unfrozen — only the state pointer moves. The revise event records `invalidated_artifact_families` naming what must be re-approved on the way forward — check it with `channel_state.py show` before re-walking.
   ABANDON_DIRECTION routes via `tools/channel_state.py abandon channels/<channel_id> --actor "<user>" --decision-ref <same-ref> --reason "..." --yes`, and is terminal — there is no un-abandon.
5. On GO, cross the workflow's second human gate, then freeze (each with explicit confirmation):
   ```
   .venv/bin/python tools/channel_state.py advance channels/<channel_id> CHANNEL_FREEZE --next-action "..." --actor "<user>" --reason "..." --prerequisite-ref channels/<channel_id>/pilots/<pilot-id>/pilot.json --human-decision-ref <the-same-real-reference>
   .venv/bin/python tools/pilot.py freeze channels/<channel_id> <pilot-id> --new-channel-version <next-version> --frozen-by "<user>" --yes
   ```
    Retrying a freeze at the same version with unchanged content completes
    idempotently (crash-safe); the same version with *changed* content is
    refused — freeze it as a new version, or pass `--force` to replace the
    release deliberately. Treat any refusal as a signal, not an error to
    route around. A production change under a GO archives the review and
    restores "needs review", and unfreezes the pilot (the frozen release is
    preserved on disk under `releases/`) — record a new review before
    freezing again.

## Stage 10 — Readiness and Channel Ready

1. `.venv/bin/python tools/channel_readiness.py channels/<channel_id> --write`. If any item fails, it tells you exactly which and why — address that before retrying. This never writes `readiness-report.json` unless every item genuinely passes.
2. `.venv/bin/python tools/channel_state.py advance channels/<channel_id> CHANNEL_READY --next-action "Channel is ready." --actor "<user>" --reason "..." --prerequisite-ref channels/<channel_id>/readiness-report.json`.
3. `.venv/bin/python tools/validate_channel.py channels/<channel_id>` — final check: `state` should be `CHANNEL_READY`, `status` should be `COMPLETE`.

## Ongoing — Episode Production

This is a loop, not a one-time stage — it's how the channel's actual videos get made, and it
runs indefinitely after `CHANNEL_READY`. It deliberately never touches `channel.yaml`'s
`version` or the CM1 workflow state — those were already settled in Stage 10. Producing a video
is not the same event as changing the channel's identity/DNA, so **never** call
`tools/pilot.py freeze` for an ongoing episode; that tool is reserved for the one-time DNA proof
in Stage 9, and a genuine identity/DNA change later gets its own separate, deliberate re-freeze.

1. Pick the next topic — ideally citing a real, still-unrealized `opportunity_proposal` from
   niche intelligence (`channels/<channel_id>/intelligence/studies/<study-id>/opportunities/`) via
   `--opportunity-ref <opportunity-artifact-id>`. Omit `--opportunity-ref` entirely for an
   ungrounded topic (it defaults to null — do not pass an empty value).
2. `.venv/bin/python tools/episode.py plan channels/<channel_id> <episode-id> --topic "..." --target-duration-seconds <20-30> [--opportunity-ref <id>]`.
3. Build it for real — same voice-first procedure as Stage 9 step 2 (script file, `tools/voiceover.py synthesize` with the channel's established voice, user listen-check, `voiceover.py validate` against the target duration), then timed visual beats, scene-local components, a
   deterministic render — per `docs/RENDER_CONTRACT.md`, using the same evaluation contract
   tooling as Stage 9 (`tools/build_scene_candidate.py`, `tools/evaluate_scene.py`) for evidence.
   Attach it as it's produced: `.venv/bin/python tools/episode.py record-production channels/<channel_id> <episode-id> --script-ref ... --voiceover-ref ... --scene-candidate-manifest <path> --evaluation-result <path> --render-ref ...`.
4. Get the user's real GO/REVISE/ABANDON call — decision note first, then (never fabricate it):
   ```
   .venv/bin/python tools/episode.py record-review channels/<channel_id> <episode-id> --decision GO --decided-by "<user>" --decision-ref <a-real-path> --rationale "..." --yes
   ```
    REVISE means rework this episode's production and record review again once it's ready (re-recording archives the previous decision into history);
    ABANDON means this episode doesn't get made — neither routes through `channel_state.py`. Verify with `.venv/bin/python tools/episode.py validate channels/<channel_id> <episode-id>`.
    After the review, write what the episode taught the style as a `lessons/` (or `failures/`) wiki note, then `python tools/channel_style.py sync channels/<channel_id> --force` so the Obsidian style snapshot learns it (see `docs/OBSIDIAN_WIKI.md`).
5. Repeat from step 1 for the next episode. Publishing the finished render to YouTube is outside
   this skill's scope — the human does that.

## Starting the dashboard

Start it in Stage 1.5, not at the end: `python tools/dashboard/server.py --port 8420` — a local-only (127.0.0.1) creator control panel. `/overview/<channel_id>` is the control panel (header, workflow progress, next action, review queue, style snapshot, pilots/episodes, services, events, wiki shortcuts); `/channel/<id>` is the raw state/event detail; `/wiki/<id>` browses the Obsidian wiki; `/review` is the unified review queue across niche intelligence, design/script exemplars, identity candidates, asset components, pilots, and episodes. Action buttons for gated decisions (freeze/review/GO-REVISE/block/resume/etc.) require an explicit confirm step in the browser before they run — they shell out to the exact same CLI commands above via `tools/dashboard/actions.py`'s fixed whitelist, never re-implementing their logic. The whitelist covers gated decisions only; scaffolding and evidence-building steps stay in the chat walkthrough above. It is not started automatically; tell the user the command and let them open it themselves.
