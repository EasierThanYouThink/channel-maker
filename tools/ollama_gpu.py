#!/usr/bin/env python3
"""Preload Ornith in Ollama and report its real CPU/GPU placement.

Ollama chooses the accelerator automatically. This tool makes that choice
observable and gives agents a machine-readable way to require GPU placement.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any
from urllib import error, request

DEFAULT_MODEL = "ornith-1.5:9b"
DEFAULT_OPENAI_BASE = "http://localhost:11434/v1"


class OllamaError(RuntimeError):
    """A user-facing Ollama API failure."""


def native_api_base() -> str:
    """Return Ollama's native `/api` base from project-compatible settings."""
    explicit = os.environ.get("OLLAMA_API_URL")
    if explicit:
        value = explicit.rstrip("/")
    else:
        value = os.environ.get("OLLAMA_BASE_URL", DEFAULT_OPENAI_BASE).rstrip("/")
        if value.endswith("/v1"):
            value = value[:-3]
    if not value.endswith("/api"):
        value += "/api"
    return value


def _request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {} if data is None else {"Content-Type": "application/json"}
    req = request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OllamaError(f"Ollama API request failed at {url}: {exc}") from exc
    if not isinstance(result, dict):
        raise OllamaError(f"Ollama API returned an invalid response at {url}")
    if result.get("error"):
        raise OllamaError(str(result["error"]))
    return result


def preload_model(model: str, keep_alive: str, api_base: str, timeout: float) -> None:
    """Ask Ollama to load a model without generating output."""
    _request_json(
        f"{api_base.rstrip('/')}/generate",
        payload={"model": model, "stream": False, "keep_alive": keep_alive},
        timeout=timeout,
    )


def running_models(api_base: str, timeout: float) -> list[dict[str, Any]]:
    """Read Ollama's current in-memory model list."""
    result = _request_json(f"{api_base.rstrip('/')}/ps", timeout=timeout)
    models = result.get("models", [])
    if not isinstance(models, list) or not all(isinstance(item, dict) for item in models):
        raise OllamaError("Ollama /api/ps returned an invalid models list")
    return models


def _canonical_model(value: str) -> str:
    normalized = value.casefold()
    final_component = normalized.rsplit("/", 1)[-1]
    return normalized if ":" in final_component else f"{normalized}:latest"


def classify_model(model: str, models: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert Ollama's byte counts into a stable processor report."""
    wanted = _canonical_model(model)
    loaded = next(
        (
            item
            for item in models
            if _canonical_model(str(item.get("name") or item.get("model") or "")) == wanted
        ),
        None,
    )
    if loaded is None:
        return {
            "model": model,
            "loaded": False,
            "status": "not_loaded",
            "processor": "not loaded",
            "size_bytes": 0,
            "vram_bytes": 0,
            "gpu_percent": 0,
            "cpu_percent": 0,
            "gpu_accelerated": False,
            "fully_on_gpu": False,
            "advice": "Preload the model, then check again.",
        }

    size = max(0, int(loaded.get("size") or 0))
    vram = max(0, int(loaded.get("size_vram") or 0))
    gpu_percent = min(100, round(vram * 100 / size)) if size else 100 if vram else 0
    cpu_percent = 100 - gpu_percent

    if gpu_percent >= 99:
        status = "full_gpu"
        processor = "100% GPU"
        advice = "Ornith is fully GPU accelerated."
    elif gpu_percent > 0:
        status = "hybrid"
        processor = f"{cpu_percent}%/{gpu_percent}% CPU/GPU"
        advice = (
            "Ollama is using the GPU, but available VRAM limited the offload. "
            "Close other GPU-heavy applications, unload Ornith, and preload it again for a larger GPU share."
        )
    else:
        status = "cpu_only"
        processor = "100% CPU"
        advice = (
            "Ollama loaded Ornith on CPU. Verify that the GPU and driver are supported, "
            "then restart Ollama and preload the model again."
        )

    return {
        "model": model,
        "loaded": True,
        "status": status,
        "processor": processor,
        "size_bytes": size,
        "vram_bytes": vram,
        "gpu_percent": gpu_percent,
        "cpu_percent": cpu_percent,
        "gpu_accelerated": gpu_percent > 0,
        "fully_on_gpu": status == "full_gpu",
        "advice": advice,
    }


def _print_human(report: dict[str, Any]) -> None:
    print(f"model: {report['model']}")
    print(f"status: {report['status']}")
    print(f"processor: {report.get('processor', 'unknown')}")
    if report.get("error"):
        print(f"error: {report['error']}")
    elif report.get("advice"):
        print(f"next: {report['advice']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-base", help="Ollama native API base; defaults to OLLAMA_API_URL or OLLAMA_BASE_URL")
    parser.add_argument("--keep-alive", default="5m", help="How long Ollama should retain the preloaded model")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--status-only", action="store_true", help="Do not preload; inspect models already in memory")
    parser.add_argument("--require-gpu", action="store_true", help="Exit 1 unless at least part of the model is on GPU")
    parser.add_argument("--require-full-gpu", action="store_true", help="Exit 1 unless the model is fully on GPU")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    api_base = (args.api_base or native_api_base()).rstrip("/")
    try:
        if not args.status_only:
            preload_model(args.model, args.keep_alive, api_base, args.timeout)
        report = classify_model(args.model, running_models(api_base, args.timeout))
    except OllamaError as exc:
        report = {"model": args.model, "status": "error", "error": str(exc)}
        print(json.dumps(report, indent=2, sort_keys=True) if args.json else "", end="")
        if not args.json:
            _print_human(report)
        elif report:
            print()
        return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human(report)

    if not report["loaded"]:
        return 1
    if args.require_full_gpu and not report["fully_on_gpu"]:
        return 1
    if args.require_gpu and not report["gpu_accelerated"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
