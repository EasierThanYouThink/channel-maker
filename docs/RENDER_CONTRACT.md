# Render Contract

Stage 8 (pilot production) never assumes a specific rendering pipeline. A
channel declares its renderer once, at `init_channel.py --renderer <name>`
(stored at `channel.yaml`'s `production.renderer`), and every asset component
registered for that channel (`tools/asset_registry.py register --renderer
<name>`) is expected to target it. `remotion` is one valid choice — this repo
was originally generalized from a Remotion-based pipeline — but any renderer
name is accepted; nothing in `engine/` or `tools/` special-cases it.

What Stage 8 actually requires is evidence in two shapes, validated by
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
