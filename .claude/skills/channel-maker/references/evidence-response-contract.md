# Hermes Collection Response Contract

After claiming a job with `tools/run_hermes_job_queue.py claim`, write exactly
two files at the `response_path` and `runtime_metadata_path` the claim printed.

## Response file (`response_path`)

```json
{
  "worker": "claude.hermes_agent",
  "model": "ornith-1.5:9b",
  "model_version": "<from `ollama show ornith-1.5:9b`, or the closest identifier available>",
  "prompt_version": "hermes-youtube-market-collection-v1",
  "hermes_version": "<from `hermes --version`>",
  "collected_at": "<ISO8601 UTC timestamp of collection>",
  "channels": [
    {
      "source_id": "UCxxxxxxxx",
      "url": "https://www.youtube.com/channel/UCxxxxxxxx",
      "channel_name": "Some Channel",
      "sample_role": "GROWTH_CANDIDATE",
      "sample_rationale": "One sentence explaining why this role was assigned.",
      "public_fields": {
        "subscriber_count": 84000,
        "public_video_count": 212,
        "created_at": null,
        "observed_uploads_per_30d": 6.0,
        "shorts_fraction": 0.9
      }
    }
  ],
  "videos": [
    {
      "channel_source_id": "UCxxxxxxxx",
      "source_id": "abc123",
      "url": "https://www.youtube.com/shorts/abc123",
      "title": "...",
      "format": "SHORTS",
      "sample_role": "BREAKOUT",
      "sample_rationale": "One sentence explaining why this role was assigned.",
      "public_fields": {
        "published_at": "2026-06-01T00:00:00+00:00",
        "duration_seconds": 42.0,
        "views": 950000,
        "likes": null,
        "comment_count": null,
        "description": null,
        "age_at_observation_days": 12.4
      }
    }
  ]
}
```

Rules:

- `worker`, `model`, `prompt_version`, `collected_at` are required and must
  be non-empty — `run_hermes_job_queue.py complete` and
  `niche_intelligence.py import-evidence` both reject a response missing them.
- Leave any `public_fields` value `null` when it is genuinely unknown or
  unavailable rather than guessing — `import-evidence` computes
  `unknown_fields` from whichever fields are `null`.
- **Never** put a private metric (CTR, retention curve, swipe-away rate,
  average % viewed, traffic sources, subscriber conversion) into this file —
  they have no field here at all; `import-evidence` always marks the full
  fixed set as `unavailable_private_metrics` on every video regardless of
  what you write.
- `sample_role` must be one of the roles the study's `sampling_policy` allows
  (`--channel-role`/`--video-role` passed to `tools/init_niche_study.py`) —
  an invalid role will fail validation at import time.
- `channels`/`videos` may be empty lists; you can run multiple collection
  jobs and import calls to grow one study incrementally.

## Runtime metadata file (`runtime_metadata_path`)

```json
{
  "status": "complete",
  "worker": "claude.hermes_agent",
  "runtime": "hermes-agent",
  "model": "ornith-1.5:9b",
  "request_sha256": "<sha256 of the request file this job was built from>",
  "ended_at": "<ISO8601 UTC timestamp>",
  "review_required": true
}
```

All seven keys are required — `run_hermes_job_queue.py complete` checks for
their presence (not their values) before moving the job to `completed/`.
`review_required` should always be `true`: nothing in this pipeline ever
skips the human review step in `niche_intelligence.py import-evidence
--reviewed-by`.
