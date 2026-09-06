# Security

This project runs locally (CLI tools plus a 127.0.0.1-only dashboard) and
holds no credentials by design: TTS and research models run on-device or
through the user's own Hermes/Ollama setup, and there are no API keys in this
repository.

## Reporting

If you find a vulnerability — especially anything that lets fabricated human
approvals pass a gate, bypass the `--yes`/TTY confirmations, or exfiltrate
data through the dashboard server — please report it privately to the
maintainer (see the commit email) rather than opening a public issue. Include
steps to reproduce against a fresh clone.

## Scope notes

- The dashboard binds `127.0.0.1` only; do not expose it to a network.
- Dashboard mutations require a per-process token embedded in the served page,
  `application/json`, and a loopback same-origin request whenever the browser
  supplies an `Origin` header. Browser confirmation remains a user-experience
  gate; the server-side token is the anti-forgery boundary.
- `data/local/` and `channels/*/` are git-ignored runtime state; review them
  before sharing or publishing a channel package.
- Voice models auto-download from an immutable Hugging Face revision on first
  synthesis. SHA-256 hashes for both the model and its configuration are pinned
  in `engine/voiceover/voiceover.py`; downloads are verified before an atomic
  install, and any mismatch is rejected as a potential supply-chain issue.
