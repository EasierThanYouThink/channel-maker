# Local Workers

Collection work (web research, transcription, annotation) runs through local
worker CLIs with a strict request → queue → response → separately-reviewed
import pattern. The worker that collects never imports its own output.

## Hermes job queue (YouTube/web research)

1. `tools/build_niche_collection_request.py` writes a collection request describing what to gather.
2. `tools/submit_hermes_job.py` enqueues it under `data/local/hermes-queue/` (git-ignored).
3. `tools/run_hermes_job_queue.py claim --next` claims one pending job and prints where the response and runtime-metadata files must be written.
4. The agent drives Hermes live (see `.claude/skills/channel-maker/references/hermes-setup.md` for environment setup) and writes both files in the shape documented in `.claude/skills/channel-maker/references/evidence-response-contract.md`.
5. `tools/run_hermes_job_queue.py complete <job_id>` — or `fail <job_id> --error "..."` if collection failed. Never complete with invented data.
6. `tools/niche_intelligence.py import-evidence … --reviewed-by "<real human>"` imports the response only after the raw numbers were shown to the user.

Hermes needs [Hermes Agent](https://hermes-agent.nousresearch.com) plus a local
model (the reference setup uses Ollama `ornith-1.5:9b`). If Hermes cannot run
a clean one-shot task, fall back to direct collection and write the same
response shape by hand — the contract is the file format, not the tool.
