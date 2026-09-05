# Channel Identity: Logo and Description

Every Channel Package carries one identity artifact
(`channels/<id>/identity/channel-identity.yaml`), validated against
`engine/identity/contracts/channel-identity.schema.json` and driven by
`tools/channel_identity.py`. It exists to produce the two things a real
YouTube channel needs that nothing earlier in the lifecycle makes: a
logo/profile picture and a written About-page description.

Identity discovery only starts once Foundation (Stage 4), Script DNA (Stage 5),
and Visual DNA (Stage 6) are frozen — a logo needs the frozen color language,
typography, and visual identity to be consistent, and the description needs
the frozen Script DNA voice. It is not a fresh creative decision made in
isolation.

## The domain-gate mechanism

Identical in shape to Visual/Motion DNA (see `docs/CHANNEL_DESIGN_DNA.md`), but
with two domains: `logo` and `description`. Each tracks:

```
discovery_status: UNPOPULATED | ACTIVE | POPULATED
authority_status: UNFROZEN | FROZEN
gate: ACTIVE_DISCOVERY | WAITING_FOR_HUMAN | HUMAN_FROZEN
inputs_required: [...]
reference_ids: [...]   # approved candidate IDs attached to this domain
decision_refs: [...]   # real human decision references recorded at freeze
```

Freezing a domain (`tools/channel_identity.py freeze-domain`) requires a real
`--decision-ref`, exactly like every other domain freeze in this repo — never
fabricated. `CHANNEL_READY` requires both `logo` and `description` frozen
(`engine/readiness/checklist.py`'s `identity_frozen` item).

## Candidate review flow

Candidates — a logo image or a description text — move through the same
lifecycle as design exemplars, driven by `tools/channel_identity.py` and
stored by `ChannelIdentityStore` (`engine/identity/store.py`) under
`channels/<id>/identity/candidates/{assets,records,reviews}`:

```
experimental → human review (approve / reject / borderline, with a reason) → approved / rejected / borderline
```

Only `approved` candidates may be attached to a domain via
`tools/channel_identity.py add-reference`.

## Generation is tool-agnostic, on purpose

Nothing in `engine/identity/` or `tools/channel_identity.py` assumes a
specific image-generation API. A logo candidate can come from whatever image
capability is available in the session, or the human can supply/commission
art directly — the store only cares about the resulting PNG/JPEG/WebP file
and its provenance record (`provenance.kind`: `human_supplied_original`,
`ai_generated_original`, or `project_original_render`). This mirrors
`docs/RENDER_CONTRACT.md`'s approach to pilot rendering: the artifact and its
review are the contract, never a specific tool.

## What's out of scope

A channel art/banner image is not produced by this stage. It was considered
and deliberately deferred — logo + description alone are what's required for
`CHANNEL_READY`; banner art can be added by hand later using the same
candidate-store pattern if wanted.
