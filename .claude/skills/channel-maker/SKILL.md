---
name: channel-maker
description: Create a new YouTube channel or study/clone an existing channel's niche and market, using Hermes Agent for public research, and walk it through this repo's full CM1 workflow from CHANNEL_INIT to CHANNEL_READY — niche intelligence, channel foundation, Script/Visual/Motion DNA discovery, channel identity, the starter asset library, and pilot production/review/freeze — then keep producing ongoing episodes, plus a local dashboard. Use when the user wants to start a new YouTube channel, research a niche or competitor channel, set up Hermes Agent for channel market research, or produce another episode for an already-ready channel.
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

1. Confirm the repo's own environment is sane (`.venv` exists, `tools/check.py` importable).
2. `which hermes`. If missing, tell the user to install Hermes Agent from hermes-agent.nousresearch.com and stop here — do not guess an install command.
3. **Hard requirement:** run `hermes --help`, `hermes skills --help`, `hermes config --help` to discover the real CLI surface before running any task command. Do not guess flags.
4. `ollama list | grep ornith-1.5`; if absent, confirm with the user then `ollama pull ornith-1.5:9b` (~6.6GB).
5. Configure `~/.hermes/config.yaml` so Hermes uses the local model, using whatever syntax step 3 discovered (a `providers.custom` block pointing `base_url` at `http://localhost:11434/v1` with `model: "custom/ornith-1.5:9b"` is the expected shape, but confirm against the real CLI/config help rather than assuming).
6. Interactively install whatever Hermes skills cover web search, YouTube data, and screenshots — confirm each prompt with the user rather than silently accepting defaults.
7. **Go/no-go smoke test:** have Hermes fetch one public YouTube channel page and confirm it returns something sensible. If Hermes has no clean one-shot "run task, get structured output" mode, tell the user and fall back to collecting directly via WebFetch/WebSearch in Stage 2, using Hermes only for whatever it's confirmed to do well.

Do not proceed to Stage 1 until step 7 succeeds or the user explicitly accepts the WebFetch/WebSearch fallback.

## Stage 1 — Intent + Channel Scaffold

1. Ask the user: **CREATE** a new channel (niche-driven), or **CLONE** — study one existing target channel? For CLONE, ask for the target channel's identity/URL *and*, separately, the new channel's own id/name/niche — these are two different things; never conflate them.
2. Collect: `channel_id` (lowercase, e.g. `my-science-shorts`), display name, primary niche, archetype (`ILLUSTRATED_EXPLAINER` / `DATA_STORY` / `MAP_STORY`), language (default `en`), formats (default `SHORTS`), and the renderer this channel's pilots will use (e.g. `remotion` — see `docs/RENDER_CONTRACT.md`; any name is valid as long as Stage 8's evidence matches the contract).
3. Run:
   ```
   .venv/bin/python tools/init_channel.py <channel_id> --name "<name>" --niche-primary "<niche>" \
     --archetype <ARCHETYPE> --creation-mode <ORIGINAL|EXISTING_CHANNEL> --renderer <renderer>
   ```
   (`ORIGINAL` for CREATE, `EXISTING_CHANNEL` for CLONE.)
4. `.venv/bin/python tools/validate_channel.py channels/<channel_id>` to confirm.
5. `.venv/bin/python tools/channel_state.py advance channels/<channel_id> NICHE_INTELLIGENCE --next-action "Run Hermes-driven niche research." --actor "<user or 'claude'>" --reason "Channel initialized."`

## Stage 2 — Hermes-Driven Niche Intelligence

1. Scaffold the study:
   ```
   .venv/bin/python tools/init_niche_study.py channels/<channel_id> --study-id <study-id> \
     --niche "<niche>" --archetype <ARCHETYPE> --format SHORTS --language en \
     --channel-role GROWTH_CANDIDATE --channel-role BASELINE_COMPARATOR \
     --video-role BREAKOUT --video-role CHANNEL_BASELINE \
     --window-from <ISO8601> --window-to <ISO8601>
   ```
2. Build the collection request describing what to go collect (niche keywords for CREATE, the one target channel for CLONE):
   ```
   .venv/bin/python tools/build_niche_collection_request.py --mode <CREATE|CLONE> \
     --channel-id <channel_id> --study-id <study-id> --target "<niche keywords or channel URL>" \
     --allowed-channel-role GROWTH_CANDIDATE --allowed-channel-role BASELINE_COMPARATOR \
     --allowed-video-role BREAKOUT --allowed-video-role CHANNEL_BASELINE \
     --output data/local/hermes-queue/requests/<slug>.json
   ```
3. `.venv/bin/python tools/submit_hermes_job.py data/local/hermes-queue/requests/<slug>.json`
4. `.venv/bin/python tools/run_hermes_job_queue.py claim --next` — note the printed `response_path`/`runtime_metadata_path`.
5. Drive Hermes live (per the CLI surface discovered in Stage 0) to collect public channel/video stats for the target. **Never record private analytics** (CTR, retention, swipe-away rate, average % viewed, traffic sources, subscriber conversion) — leave a field `null` if only a private version is available.
6. Write the response and runtime-metadata files yourself in the exact shape documented in [references/evidence-response-contract.md](references/evidence-response-contract.md).
7. `.venv/bin/python tools/run_hermes_job_queue.py complete <job_id>`.
8. **Show the user the raw collected numbers before importing — this is the real manual-review moment**, not a formality.
9. `.venv/bin/python tools/niche_intelligence.py import-evidence channels/<channel_id>/intelligence/studies/<study-id> <response_path> --reviewed-by "<the user's real name>"`. This fails loudly if `--reviewed-by` is empty — never fabricate a name.
10. Optionally, for a flagged breakout video: `.venv/bin/python tools/niche_intelligence.py relative-views <request.json>`.
11. Synthesize the interpretive chain from the imported evidence (a real opportunity map cannot come from raw evidence alone):
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
12. `.venv/bin/python tools/niche_intelligence.py validate channels/<channel_id>/intelligence/studies/<study-id>` must pass before Stage 3.

Sample-role assignment (`GROWTH_CANDIDATE`, `BREAKOUT`, etc.) is a judgment call — there is no deterministic threshold in this repo's philosophy (`docs/NICHE_INTELLIGENCE.md`). Use your own analysis and say so plainly.

## Stage 3 — Opportunity Map + Human Gate

1. `.venv/bin/python tools/niche_intelligence.py publish-summaries channels/<channel_id> channels/<channel_id>/intelligence/studies/<study-id>`.
2. Summarize the opportunity map for the user conversationally from those wiki pages / the `opportunity_proposal` artifacts.
3. Get the user's real strategy decision. Record it somewhere real (e.g. a short markdown note, or point at the opportunity wiki page) — `human_decision_ref` must reference something real, never a fabricated string.
4. `.venv/bin/python tools/channel_state.py advance channels/<channel_id> STRATEGY_SELECTION --next-action "<next action>" --actor "<user>" --reason "<reason>" --prerequisite-ref <path-to-opportunity-map-evidence> --human-decision-ref <the-real-reference>`.
5. `.venv/bin/python tools/validate_channel.py channels/<channel_id>` as a final check.

## Stage 4 — Channel Foundation

1. Draft the conceptual identity layer with the user (audience, promise, personality, differentiation, emotional goal, boundaries, what the channel deliberately avoids):
   ```
   .venv/bin/python tools/channel_foundation.py write channels/<channel_id> \
     --audience-description "..." --promise "..." --niche-primary "<niche>" \
     --personality <trait> [--personality <trait> ...] --balance <MOSTLY_EDUCATIONAL|BALANCED|MOSTLY_ENTERTAINMENT> \
     --differentiation "..." --emotional-goal "..." --content-boundary "..." \
     --primary-format SHORTS --avoids "..."
   ```
2. Get the user's real sign-off and attach it: `.venv/bin/python tools/channel_foundation.py attach-decision channels/<channel_id> --decision-ref <a-real-path>`.
3. `.venv/bin/python tools/channel_state.py advance channels/<channel_id> SCRIPT_DNA_DISCOVERY --next-action "..." --actor "<user>" --reason "..." --prerequisite-ref channels/<channel_id>/strategy/foundation.yaml`.

## Stage 5 — Script DNA Discovery

1. Draft candidate scripting identity: `.venv/bin/python tools/script_dna.py write channels/<channel_id> --hook-philosophy "..." --narrator-personality <trait> ... --sentence-length-qualitative "..." --technical-depth "..." --humor-level "..." --information-density "..." --question-usage "..." --number-usage "..." --story-structure "..." --ending-behavior "..." --cta-philosophy "..." --fact-verification-requirements "..."` (add `--preferred-cliche`/`--forbidden-cliche`/`--unresolved-variable` as needed).
2. Optionally collect candidate opening lines as examples: `tools/script_dna.py add-example channels/<channel_id> --text "..." --provenance-kind <human_authored|model_drafted|adapted_from_evidence> --created-by "<you>" --source-ref "..."`, then `tools/script_dna.py review-example channels/<channel_id> <example_id> --decision <approved|rejected|borderline> --reviewer "<user>" --reason "..."` (interactive confirm, or `--yes` if already confirmed with the user in chat).
3. Freeze once the user is satisfied: `.venv/bin/python tools/script_dna.py freeze channels/<channel_id> --decision-ref <a-real-path>` (interactive confirm, or `--yes`).
4. `.venv/bin/python tools/channel_state.py advance channels/<channel_id> VISUAL_DNA_DISCOVERY --next-action "..." --actor "<user>" --reason "..." --prerequisite-ref channels/<channel_id>/script/script-dna.yaml`.

## Stage 6 — Visual + Motion DNA Discovery

Visual DNA has five domains (`visual_identity`, `typography`, `color_language`, `composition_grammar`, `scene_aesthetics`); Motion DNA has one (`motion_identity`) — separate artifacts, per `docs/CHANNEL_DESIGN_DNA.md`. For each:

1. `.venv/bin/python tools/design_dna.py <visual|motion> init channels/<channel_id>`.
2. Discovery loop per domain: create/gather candidate reference images, register them (`tools/design_exemplars.py --channel <channel_id> add <image> --title "..." --domain <domain> --provenance-kind <...> --created-by "<you>" --source-ref "..."`), show the user, get their approve/reject/borderline call (`tools/design_exemplars.py --channel <channel_id> review <exemplar_id> --decision ... --reviewer "<user>" --reason "..."`), then `tools/design_dna.py <visual|motion> add-reference channels/<channel_id> --domain <domain> --exemplar-id <exemplar_id>` for approved ones. Narrow and repeat until the user is satisfied — do not invent a fixed number of rounds.
3. Freeze each domain only when the user explicitly says so: `tools/design_dna.py <visual|motion> freeze-domain channels/<channel_id> --domain <domain> --decision-ref <a-real-path>` (interactive confirm, or `--yes`).
4. `tools/design_dna.py <visual|motion> check-ready channels/<channel_id>` must report all domains frozen before advancing.
5. `.venv/bin/python tools/channel_state.py advance channels/<channel_id> MOTION_DNA_DISCOVERY --prerequisite-ref channels/<channel_id>/design/visual-dna-seed.yaml ...` after visual is fully frozen, then `... advance channels/<channel_id> CHANNEL_IDENTITY --prerequisite-ref channels/<channel_id>/motion/motion-dna-seed.yaml ...` after motion is fully frozen.

## Stage 7 — Channel Identity

Only starts once Foundation, Script DNA, and Visual DNA are frozen — see
`docs/CHANNEL_IDENTITY.md`. Two domains: `logo` (an image) and `description` (a
short About-page bio, in the frozen Script DNA voice).

1. `.venv/bin/python tools/channel_identity.py init channels/<channel_id>`.
2. Discovery loop per domain: produce/gather candidates (a logo image, or a draft description string), register them (`tools/channel_identity.py add --channel <channel_id> --domain <logo|description> --title "..." [--image <path> | --text "..."] --provenance-kind <...> --created-by "<you>" --source-ref "..."`), show the user, get their approve/reject/borderline call (`tools/channel_identity.py review --channel <channel_id> <candidate_id> --decision ... --reviewer "<user>" --reason "..."`), then `tools/channel_identity.py add-reference channels/<channel_id> --domain <domain> --candidate-id <candidate_id>` for approved ones. Narrow and repeat until the user is satisfied — do not invent a fixed number of rounds.
3. Freeze each domain only when the user explicitly says so: `tools/channel_identity.py freeze-domain channels/<channel_id> --domain <domain> --decision-ref <a-real-path>` (interactive confirm, or `--yes`).
4. `tools/channel_identity.py check-ready channels/<channel_id>` must report both domains frozen before advancing.
5. `.venv/bin/python tools/channel_state.py advance channels/<channel_id> STARTER_VISUAL_LIBRARY --prerequisite-ref channels/<channel_id>/identity/channel-identity.yaml ...`.

## Stage 8 — Starter Visual Library

Only create a component when a real, immediate need exists (never a speculative catalog):

1. `.venv/bin/python tools/asset_registry.py register --scope CHANNEL --channel-id <channel_id> --category <primitive|object|character|diagram|mechanism|effect> --name "..." --description "..." --renderer <renderer> --source-kind tsx --source-path <renderer>/src/channels/<channel_id>/<Name>.tsx --export <ExportName> --justification "..."` after actually writing the component.
2. Get the user's review: `tools/asset_registry.py review <component_path> --decision <approved|rejected|deprecated> --reviewer "<user>" --reason "..."`.
3. `.venv/bin/python tools/channel_state.py advance channels/<channel_id> PILOT_PLAN --prerequisite-ref <approved-component-path> ...` once at least one component is approved.

## Stage 9 — Pilot Plan, Production, Review

1. `.venv/bin/python tools/pilot.py plan channels/<channel_id> <pilot-id> --topic "..." --target-duration-seconds <20-30> --integration-goal "Prove Script DNA" --integration-goal "Prove Visual DNA" ...`, then `channel_state.py advance ... PILOT_PLAN` (already done in step 3 above if this is the first pilot) `-> PILOT_PRODUCTION`.
2. Build the pilot with the channel's declared renderer — script, voiceover, timed visual beats, scene-local components, a deterministic render — per the contract in `docs/RENDER_CONTRACT.md`, using the evaluation contract tooling (`tools/build_scene_candidate.py`, `tools/evaluate_scene.py`) for evidence. Attach evidence as it's produced: `.venv/bin/python tools/pilot.py record-production channels/<channel_id> <pilot-id> --script-ref ... --scene-candidate-manifest <path> --evaluation-result <path> --render-ref ...`.
3. `.venv/bin/python tools/channel_state.py advance channels/<channel_id> PILOT_REVIEW --prerequisite-ref channels/<channel_id>/pilots/<pilot-id>/pilot.json ...`.
4. Get the user's real GO/REVISE/ABANDON_DIRECTION decision — never fabricate it:
   ```
   .venv/bin/python tools/pilot.py record-review channels/<channel_id> <pilot-id> --decision GO --decided-by "<user>" --decision-ref <a-real-path> --rationale "..."
   ```
   REVISE requires `--revise-target <STATE>` (one of the states this pilot passed through) and routes via `tools/channel_state.py revise channels/<channel_id> <STATE> --decision-ref <same-ref> --next-action "..." --reason "..."`. ABANDON_DIRECTION routes via `tools/channel_state.py abandon channels/<channel_id> --decision-ref <same-ref> --reason "..."`.
5. On GO: `.venv/bin/python tools/channel_state.py advance channels/<channel_id> CHANNEL_FREEZE --prerequisite-ref channels/<channel_id>/pilots/<pilot-id>/pilot.json --human-decision-ref <the-same-real-reference>` (this is the one state-machine human gate in this whole range), then `.venv/bin/python tools/pilot.py freeze channels/<channel_id> <pilot-id> --new-channel-version <next-version> --frozen-by "<user>"`.

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
   `--opportunity-ref <opportunity-artifact-id>`; a topic with no such grounding is fine too, just
   pass `--opportunity-ref` as nothing.
2. `.venv/bin/python tools/episode.py plan channels/<channel_id> <episode-id> --topic "..." --target-duration-seconds <20-30> [--opportunity-ref <id>]`.
3. Build it for real — script, voiceover, timed visual beats, scene-local components, a
   deterministic render — per `docs/RENDER_CONTRACT.md`, using the same evaluation contract
   tooling as Stage 9 (`tools/build_scene_candidate.py`, `tools/evaluate_scene.py`) for evidence.
   Attach it as it's produced: `.venv/bin/python tools/episode.py record-production channels/<channel_id> <episode-id> --script-ref ... --scene-candidate-manifest <path> --evaluation-result <path> --render-ref ...`.
4. Get the user's real GO/REVISE/ABANDON call — never fabricate it:
   ```
   .venv/bin/python tools/episode.py record-review channels/<channel_id> <episode-id> --decision GO --decided-by "<user>" --decision-ref <a-real-path> --rationale "..."
   ```
   REVISE means rework this episode's production and record review again once it's ready;
   ABANDON means this episode doesn't get made — neither routes through `channel_state.py`.
5. Repeat from step 1 for the next episode. Publishing the finished render to YouTube is outside
   this skill's scope — the human does that.

## Starting the dashboard

`.venv/bin/python tools/dashboard/server.py --port 8420` — a local-only (127.0.0.1), read-mostly control panel: channel list, per-channel state/next-action/event-log, wiki browsing, and a unified review queue across niche intelligence, design/script exemplars, identity candidates, asset components, pilots, and episodes. Action buttons for gated decisions (freeze/review/GO-REVISE/etc.) require an explicit confirm step in the browser before they run — they shell out to the exact same CLI commands above via `tools/dashboard/actions.py`'s fixed whitelist, never re-implementing their logic. It is not started automatically; tell the user the command and let them open it themselves.
