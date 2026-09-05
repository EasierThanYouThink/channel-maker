# Channel Design DNA: Visual/Motion Discovery

Each Channel Package carries two design-identity artifacts, kept separate because
visual and motion decisions freeze on different timelines and by different people:

- **Visual DNA** (`channels/<id>/design/visual-dna-seed.yaml`) — five domains:
  `visual_identity`, `typography`, `color_language`, `composition_grammar`,
  `scene_aesthetics`.
- **Motion DNA** (`channels/<id>/motion/motion-dna-seed.yaml`) — one domain:
  `motion_identity`.

Both are validated against `engine/design/contracts/visual-dna-seed.schema.json`
and `motion-dna-seed.schema.json` respectively, and driven by `tools/design_dna.py`.

## The domain-gate mechanism

Every domain in a seed artifact tracks its own gate:

```
discovery_status: UNPOPULATED | ACTIVE | POPULATED
authority_status: UNFROZEN | FROZEN
gate: AWAITING_HUMAN_STYLE_SEED | ACTIVE_DISCOVERY | WAITING_FOR_HUMAN | HUMAN_FROZEN
inputs_required: [...]   # what still needs to be gathered
reference_ids: [...]     # approved exemplar IDs attached to this domain
decision_refs: [...]     # real human decision references recorded at freeze
```

A domain starts `UNPOPULATED`/`UNFROZEN`. Attaching an approved exemplar moves
`discovery_status` to `ACTIVE`. Freezing a domain (`tools/design_dna.py <visual|motion>
freeze-domain`) requires a real `--decision-ref`, sets `discovery_status: POPULATED`
and `authority_status: FROZEN`, and records the decision reference — never
fabricated, always a real path or note the human provided. A channel's Visual (or
Motion) DNA is only "ready" once every domain in it is `FROZEN`
(`tools/design_dna.py <visual|motion> check-ready`).

## Exemplar review flow

Candidate reference images move through one lifecycle, driven by
`tools/design_exemplars.py` and stored by `ChannelExemplarStore`
(`engine/design/exemplars.py`) under
`channels/<id>/design/exemplars/{assets,records,reviews}`:

```
experimental → human review (approve / reject / borderline, with a reason) → approved / rejected / borderline
```

Only `approved` exemplars may be attached to a domain's `reference_ids` via
`tools/design_dna.py <visual|motion> add-reference`. Nothing here fabricates a
reviewer name or a decision — every review call requires a real `--reviewer` and
`--reason`, enforced in code.
