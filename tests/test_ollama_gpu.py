"""Tests for the cross-platform Ollama GPU diagnostic."""

from __future__ import annotations

import json
from pathlib import Path

from tools import ollama_gpu


def test_native_api_base_derives_from_openai_compatible_url(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_API_URL", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://example.test:11434/v1/")

    assert ollama_gpu.native_api_base() == "http://example.test:11434/api"


def test_native_api_base_honors_explicit_override(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_URL", "http://example.test:11434/api/")

    assert ollama_gpu.native_api_base() == "http://example.test:11434/api"


def test_classify_full_hybrid_cpu_and_missing_models() -> None:
    full = ollama_gpu.classify_model(
        "ornith-1.5:9b",
        [{"name": "ornith-1.5:9b", "size": 1000, "size_vram": 1000}],
    )
    hybrid = ollama_gpu.classify_model(
        "ornith-1.5:9b",
        [{"model": "ornith-1.5:9b", "size": 1000, "size_vram": 620}],
    )
    cpu = ollama_gpu.classify_model(
        "ornith-1.5:9b",
        [{"name": "ornith-1.5:9b", "size": 1000, "size_vram": 0}],
    )
    missing = ollama_gpu.classify_model("ornith-1.5:9b", [])

    assert (full["status"], full["processor"], full["gpu_percent"]) == (
        "full_gpu", "100% GPU", 100,
    )
    assert (hybrid["status"], hybrid["processor"], hybrid["gpu_percent"]) == (
        "hybrid", "38%/62% CPU/GPU", 62,
    )
    assert (cpu["status"], cpu["processor"], cpu["gpu_accelerated"]) == (
        "cpu_only", "100% CPU", False,
    )
    assert (missing["status"], missing["loaded"]) == ("not_loaded", False)


def test_preload_uses_empty_native_generate_request(monkeypatch) -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return b'{"done":true}'

    def fake_urlopen(request, timeout):
        captured.update(url=request.full_url, body=json.loads(request.data), timeout=timeout)
        return Response()

    monkeypatch.setattr(ollama_gpu.request, "urlopen", fake_urlopen)

    ollama_gpu.preload_model("ornith-1.5:9b", "10m", "http://localhost:11434/api", 123)

    assert captured == {
        "url": "http://localhost:11434/api/generate",
        "body": {"model": "ornith-1.5:9b", "stream": False, "keep_alive": "10m"},
        "timeout": 123,
    }


def test_preload_can_request_gpu_or_cpu_placement(monkeypatch) -> None:
    bodies = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return b'{"done":true}'

    def fake_urlopen(request, timeout):
        bodies.append(json.loads(request.data))
        return Response()

    monkeypatch.setattr(ollama_gpu.request, "urlopen", fake_urlopen)

    ollama_gpu.preload_model(
        "ornith-1.5:9b", "5m", "http://localhost:11434/api", 30, processor="gpu"
    )
    ollama_gpu.preload_model(
        "ornith-1.5:9b", "5m", "http://localhost:11434/api", 30, processor="cpu"
    )

    assert bodies[0]["options"] == {"num_gpu": -1}
    assert bodies[1]["options"] == {"num_gpu": 0}


def test_running_models_reads_native_process_endpoint(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return b'{"models":[{"name":"ornith-1.5:9b"}]}'

    monkeypatch.setattr(
        ollama_gpu.request,
        "urlopen",
        lambda request, timeout: Response(),
    )

    assert ollama_gpu.running_models("http://localhost:11434/api", 5) == [
        {"name": "ornith-1.5:9b"}
    ]


def test_main_preloads_and_accepts_hybrid_gpu(monkeypatch, capsys) -> None:
    preloaded = []
    monkeypatch.setattr(
        ollama_gpu,
        "preload_model",
        lambda model, keep_alive, api_base, timeout, processor: preloaded.append((model, processor)),
    )
    monkeypatch.setattr(
        ollama_gpu,
        "running_models",
        lambda api_base, timeout: [
            {"name": "ornith-1.5:9b", "size": 1000, "size_vram": 500}
        ],
    )

    assert ollama_gpu.main(["--json", "--require-gpu"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert preloaded == [("ornith-1.5:9b", "auto")]
    assert report["status"] == "hybrid"


def test_main_can_require_full_gpu(monkeypatch, capsys) -> None:
    monkeypatch.setattr(ollama_gpu, "preload_model", lambda *_args: None)
    monkeypatch.setattr(
        ollama_gpu,
        "running_models",
        lambda *_args: [{"name": "ornith-1.5:9b", "size": 1000, "size_vram": 500}],
    )

    assert ollama_gpu.main(["--json", "--require-full-gpu"]) == 1
    assert json.loads(capsys.readouterr().out)["fully_on_gpu"] is False


def test_main_enforces_selected_cpu_or_gpu_placement(monkeypatch, capsys) -> None:
    requested = []
    monkeypatch.setattr(
        ollama_gpu,
        "preload_model",
        lambda model, keep_alive, api_base, timeout, processor: requested.append(processor),
    )
    monkeypatch.setattr(
        ollama_gpu,
        "running_models",
        lambda *_args: [{"name": "ornith-1.5:9b", "size": 1000, "size_vram": 0}],
    )

    assert ollama_gpu.main(["--json", "--processor", "cpu"]) == 0
    assert json.loads(capsys.readouterr().out)["requested_processor"] == "cpu"
    assert ollama_gpu.main(["--json", "--processor", "gpu"]) == 1
    assert json.loads(capsys.readouterr().out)["requested_processor"] == "gpu"
    assert requested == ["cpu", "gpu"]


def test_main_reports_api_failure_without_traceback(monkeypatch, capsys) -> None:
    def fail(*_args):
        raise ollama_gpu.OllamaError("Ollama is unavailable")

    monkeypatch.setattr(ollama_gpu, "preload_model", fail)

    assert ollama_gpu.main(["--json"]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "model": "ornith-1.5:9b",
        "requested_processor": "auto",
        "status": "error",
        "error": "Ollama is unavailable",
    }


def test_skill_requires_an_explicit_gpu_or_cpu_choice() -> None:
    skill = (Path(__file__).parents[1] / ".claude/skills/channel-maker/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "Ask the user to choose the Ornith processor" in skill
    assert "GPU (recommended)" in skill
    assert "at least 8 GB of free" in skill
    assert "--processor gpu --require-full-gpu" in skill
    assert "--processor cpu" in skill
