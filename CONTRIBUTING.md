# Contributing

This repo is a Claude Code skill plus its supporting engine. The skill text in
`.claude/skills/channel-maker/SKILL.md` is load-bearing documentation: a
`tests/test_skill_walkthrough.py` test executes the documented path literally,
so **any skill change that alters commands, flags, stage order, or transitions
must update that test first** (write the failing walkthrough, then fix the
skill or the code).

## Rules

- Evidence first: every interpretation claim needs a resolvable source; no AI
  output, score, or metric creates human approval — freezes, reviews, and
  GO/REVISE/ABANDON calls require a real human decision reference resolving to
  a real repository file, enforced in code.
- Smallest reviewable change per commit; keep commits green (`python
  tools/check.py`).
- Schemas and contracts are versioned explicitly; never silently widen an enum
  or loosen a gate.
- No live scrapers in this repo: public web research goes through the
  Hermes-driven queue with human-reviewed import, or is hand-written per
  `.claude/skills/channel-maker/references/evidence-response-contract.md`.
- Never commit `channels/*/`, `data/local/` contents (beyond `.gitkeep`),
  `.venv/`, model downloads, API keys, or private analytics. If it's not
  covered by `.gitignore`, don't `git add` it blindly — check `git status`.
- Voice: one voice per channel; timing evidence is measured from real audio,
  estimates must be labeled as estimates.
- V1 is CREATE-only. CLONE/existing-channel support returns in v2; the last
  CLONE-capable tree is preserved on the `archive/clone-mode-capable` branch.
