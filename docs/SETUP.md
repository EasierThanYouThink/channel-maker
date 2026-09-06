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

## Choose Ornith GPU or CPU execution

Channel Maker asks which processor Ornith should use before configuring Hermes.
Choose GPU for substantially faster research, or CPU when accelerator memory is
unavailable. Both choices use the same model.

For `ornith-1.5:9b` at Ollama's default 4096-token context, we recommend at
least 8 GB of **free** accelerator memory—not merely 8 GB installed. That means
free VRAM on a discrete GPU or available unified memory on Apple Silicon.
Larger contexts and concurrent models require more.

After pulling Ornith, request the selected placement and verify the result:

```
python tools/ollama_gpu.py --processor gpu --require-full-gpu  # recommended
python tools/ollama_gpu.py --processor cpu                     # slower fallback
```

The command reports `full_gpu`, `hybrid`, or `cpu_only` and supports `--json`
for agents. If the GPU command reports hybrid or CPU-only placement, choose
whether to free memory and retry or deliberately accept the slower fallback.
To retry, close other GPU-heavy applications, run
`ollama stop ornith-1.5:9b`, and issue the GPU command again. `ollama ps` is the
underlying Ollama status view. See [Ollama hardware support](https://docs.ollama.com/gpu)
and [Ollama's processor-status explanation](https://docs.ollama.com/faq#how-can-i-tell-if-my-model-was-loaded-onto-the-gpu).

Hermes config (`~/.hermes/config.yaml`, `%USERPROFILE%\.hermes\config.yaml` on
Windows) — confirm against `hermes config --help` first:

```yaml
providers:
  custom:
    type: openai
    base_url: http://localhost:11434/v1
    api_key: "${OPENAI_API_KEY}"
    extra_body:
      options:
        num_gpu: -1  # GPU choice; use 0 for CPU
model: "custom/ornith-1.5:9b"
```

The `num_gpu` value must match the user's choice. Confirm that the installed
Hermes version supports this `extra_body` shape before changing its config.

PowerShell equivalents for the skill's bootstrap commands:

| Linux/macOS | Windows PowerShell |
|---|---|
| `which hermes` | `where hermes` |
| `ollama list \| grep ornith` | `ollama list \| Select-String ornith` |
| `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` |
