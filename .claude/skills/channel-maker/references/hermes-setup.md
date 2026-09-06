# Hermes Agent Setup Checklist (Windows / macOS / Linux)

Hermes Agent (https://hermes-agent.nousresearch.com) is a self-hosted CLI/desktop
scraping agent. Its exact CLI surface changes over time and was not fully
confirmed when this skill was written — treat every command below except the
presence check as provisional until discovered live in step 2.

> OS note: use `where hermes` on Windows PowerShell, `which hermes` on
> macOS/Linux. `ollama list | Select-String ornith-1.5` on PowerShell,
> `ollama list | grep ornith-1.5` elsewhere. Python commands: activate the
> venv first (`.venv\Scripts\Activate.ps1` on Windows,
> `source .venv/bin/activate` elsewhere), then `python tools/...`.
> Full per-OS setup: `docs/SETUP.md` (`python tools/setup.py --check-only`
> reports service presence without changing anything).

## 0. Machine check (run first, every session)

```
python tools/setup.py --check-only --json
```

One report: venv presence, Python version, and Hermes / Ollama / Piper /
Node availability. Act on every `MISS` in the sections below. Without
`--json` the same report prints human-readable.

```
which hermes        # macOS / Linux
where hermes        # Windows PowerShell
```

If missing: tell the user to install it from https://hermes-agent.nousresearch.com and
stop. Do not guess a package-manager install command — the distribution
mechanism (desktop app download vs. package manager) was not confirmed.

## 2. Discover the real CLI surface (hard requirement, not optional)

```
hermes --help
hermes skills --help
hermes config --help
```

Read the actual output before running anything else. Look specifically for:

- a one-shot, non-interactive way to run a single task and get structured
  output back (this is what Stage 2 needs to drive real collection);
- the exact subcommand for installing a skill (the example
  `hermes skills install <category>/<name>` is illustrative only (check the
  real help for the exact spelling — it is not `scrapling`) —
  confirm the real category/name for whatever covers web search, YouTube data,
  and screenshots);
- the exact subcommand/flags for setting the model/provider.

If no clean one-shot task-execution mode exists, tell the user plainly and
plan to fall back to Claude collecting directly via WebFetch/WebSearch in
Stage 2, using Hermes only for capabilities it's confirmed to do well
(e.g. screenshots, harder scraping targets).

## 3. Local model (ornith-1.5:9b)

```
ollama list | grep ornith-1.5            # macOS / Linux
ollama list | Select-String ornith-1.5   # Windows PowerShell
```

If absent, confirm with the user (this is a ~6.6GB download) then:

```
ollama pull ornith-1.5:9b
```

This exposes an OpenAI-compatible endpoint at `http://localhost:11434/v1`.

## 4. Point Hermes at the local model

Config lives at `~/.hermes/config.yaml` (API keys in `~/.hermes/.env`). The
expected shape, to be confirmed against what step 2 actually revealed:

```yaml
providers:
  custom:
    type: openai
    base_url: http://localhost:11434/v1
    api_key: "${OPENAI_API_KEY}"
model: "custom/ornith-1.5:9b"
```

A dummy value in `OPENAI_API_KEY` is fine — a local Ollama endpoint typically
does not enforce it, but Hermes may still require the variable to be set.

## 5. Install the relevant Hermes skills

Run whatever step 2 revealed as the correct install command(s) for web
search, YouTube data access, and screenshots — interactively with the user,
confirming each prompt rather than silently accepting defaults.

## 6. Go/no-go smoke test

Have Hermes fetch one public YouTube channel page (any real, public channel)
and confirm the output looks like real collected data, not an error or an
empty result. Treat this as a genuine gate: a 9B local model doing reliable
structured YouTube-metadata extraction is not a given. If it fails, tell the
user and use the WebFetch/WebSearch fallback for Stage 2 instead of retrying
indefinitely.
