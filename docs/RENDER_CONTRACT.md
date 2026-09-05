# Render Contract

Stage 9 (pilot production) never assumes a specific rendering pipeline. A
channel declares its renderer once, at `init_channel.py --renderer <name>`
(stored at `channel.yaml`'s `production.renderer`), and every asset component
registered for that channel (`tools/asset_registry.py register --renderer
<name>`) is expected to target it. `remotion` is one valid choice — this repo
was originally generalized from a Remotion-based pipeline — but any renderer
name is accepted; nothing in `engine/` or `tools/` special-cases it.

What Stage 9 actually requires is evidence in two shapes, validated by
`tools/build_scene_candidate.py` and `tools/evaluate_scene.py` against
`schemas/scene_candidate_manifest.schema.json` and
`schemas/evaluation_contract.schema.json` / `evaluation_result.schema.json`,
then attached to the pilot with `tools/pilot.py record-production`:

## 1. Scene candidate manifest

One JSON artifact per rendered scene, produced by
`tools/build_scene_candidate.py`, listing:

- `generator` — which agent/model/prompt version produced the scene.
- `artifacts` — one or more evidence files (`scene_json`, `still`,
  `contact_sheet`, `video`, `narration_timing`, `audio`, `validator_output`,
  `source_packet`), each content-hashed (`sha256`) so the evidence is
  tamper-evident.

Your renderer needs to produce at least the files your evaluation contract's
requirements call for (see below) — typically a still or contact sheet for
visual review, and the rendered video itself.

## 2. Evaluation contract + result

- `evaluation_contract.schema.json`: a human-owned rubric (`dimensions`,
  `hard_gates`, pass/needs-revision `thresholds`) — you write this once per
  channel or per scene, independent of renderer.
- `evaluation_result.schema.json`: `tools/evaluate_scene.py`'s output —
  content-hashed references back to the candidate manifest and the contract,
  a `score_100`, per-dimension scores, and hard-gate outcomes. `authority` is
  always `advisory_only` — this never substitutes for the human GO/REVISE/
  ABANDON_DIRECTION call in `tools/pilot.py record-review`.

## Bringing your own renderer

To plug in a renderer other than Remotion: build whatever pipeline produces
the evidence artifacts above, point `tools/build_scene_candidate.py` at its
output files, and write an `evaluation_contract.schema.json` describing what
"good" means for your scenes. Nothing else in this repo changes.

## Adapter floor (what "a renderer" must provide)

Renderers stay independent internally, but each channel's production must
record the following so a review binds to an exact, reproducible export:

- **Declared capabilities** — renderer name and version, recorded in the
  pilot/episode production log alongside the scene manifest.
- **Reproducible invocation** — the command (or equivalent record) that turns
  pinned inputs into the export, so the same inputs rebuild the same video.
- **Pinned inputs** — every source file that feeds the render is either a
  content-hashed manifest artifact or a recorded `script_ref`/`voiceover_ref`;
  nothing enters the export from an unrecorded path.
- **Output manifest** — the export itself is attached as `render_ref` and
  must exist and be non-empty before any GO decision
  (`engine/production/completeness.py`).
- **Final-composition evaluation** — evaluate the assembled composition, not
  just individual scenes: scene order, narration mix, and timeline coverage
  against the sentence spans in the voiceover timing.

Byte-level media probing (dimensions, decoded duration, audio presence) is
future work pending a pinned probing tool — no new binary dependencies are
introduced for it in v1.

## Word-timing caveat

Voiceover word records carry a `method`: `measured_alignment` (phoneme-timed)
or `uniform_estimate` (proportionally laid out across a measured sentence
span). Downstream consumers — beats, captions, scene timing — must treat
`uniform_estimate` words as estimates: never silent-precision caption cues.
