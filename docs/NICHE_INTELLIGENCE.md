# Niche Intelligence

Offline, evidence-first market research for one Channel Package. Studies live
under `channels/<id>/intelligence/studies/<study-id>/` as versioned JSON
bundles: public channel/video evidence, sample roles, annotations, relative
performance, observations, hypotheses, and opportunity proposals — each with
its own authority class. Raw facts never become strategy; the chain is
evidence → observation → hypothesis → opportunity → (human) strategy decision.

## Sample roles are judgment calls

Channel roles (`GROWTH_CANDIDATE`, `BASELINE_COMPARATOR`) and video roles
(`BREAKOUT`, `CHANNEL_BASELINE`, …) are assigned by analysis, not by a
deterministic threshold. There is deliberately no view-count cutoff in this
repo's philosophy: a breakout is judged relative to its own channel's baseline
(see the `relative_views_same_channel` metric), and role assignment should be
stated plainly as the agent's own analysis, limitations included.

## Reference roles stay separated

`MARKET_EVIDENCE`, `CREATIVE_REFERENCE`, and `VISUAL_GROUNDING` are different
input roles. Public competitor evidence informs strategy but is never design
authority and never renderer-eligible.

## CM4 boundary

CM3 defines the evidence/output contracts. Live acquisition belongs to CM4 and
follows one rule: the collecting worker never imports its own collection.
Evidence enters a study only through `niche_intelligence.py import-evidence`
with an explicit `--reviewed-by` human reviewer, after the raw numbers were
shown to the user. Unknowns (notably all private analytics: CTR, retention,
swipe-away, conversion) stay explicit `null`s, never guesses.
