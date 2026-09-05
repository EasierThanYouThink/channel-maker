# Setup — Windows / macOS / Linux

One command on every OS (run from the repo root, no venv needed yet):

```
python tools/setup.py
```

It creates `.venv`, upgrades pip, installs `requirements.txt`, then reports the
combined-services stack. `python tools/setup.py --check-only` reports without
changing anything. `python tools/check.py` verifies afterwards.

> Never use `.venv/bin/python` directly in docs or chat — on Windows the venv
> lives at `.venv\Scripts\python.exe`. Prefer `python tools/...` with the venv
> activated, or `tools/_platform.py:project_python()` in code.

## Per-OS notes

### Windows (PowerShell)

```
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python tools/setup.py
python tools/check.py
```

- If script execution is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- Presence checks: `where hermes`, `where ollama`, `where python` (not `which`).
- Hermes config: `%USERPROFILE%\.hermes\config.yaml` (same shape as below).
- `piper-tts`/`onnx` wheels exist for Windows x64; on ARM use WSL2.

### macOS (zsh)

```
python3 -m venv .venv
source .venv/bin/activate
python tools/setup.py
python tools/check.py
```

- Presence checks: `which hermes`, `ollama list`.
- Apple Silicon: `onnx` + `piper-tts` have arm64 wheels; if pip fails, use
  `conda-forge` python or Rosetta as fallback.

### Linux (bash)

```
python3 -m venv .venv
source .venv/bin/activate
python tools/setup.py
python tools/check.py
```

## External services (all OSes — manual install, never scripted)

| Service | Why | Install |
|---|---|---|
| Hermes Agent | public web/YouTube research (Stage 2) | hermes-agent.nousresearch.com desktop/CLI build for your OS |
| Ollama + `ornith-1.5:9b` | local model Hermes points at | ollama.com download, then `ollama pull ornith-1.5:9b` (~6.6GB) |
| Node/npm | only for `remotion` renderers | nodejs.org LTS |
| Piper voice | `tools/voiceover.py` downloads `lessac-medium` (~60MB) into `data/local/piper-voices/` on first synthesize | automatic, offline after |

Hermes config (`~/.hermes/config.yaml`, `%USERPROFILE%\.hermes\config.yaml` on
Windows) — confirm against `hermes config --help` first:

```yaml
providers:
  custom:
    type: openai
    base_url: http://localhost:11434/v1
    api_key: "${OPENAI_API_KEY}"
model: "custom/ornith-1.5:9b"
```

PowerShell equivalents for the skill's bootstrap commands:

| Linux/macOS | Windows PowerShell |
|---|---|
| `which hermes` | `where hermes` |
| `ollama list \| grep ornith` | `ollama list \| Select-String ornith` |
| `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` |
