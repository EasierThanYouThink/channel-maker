"""Build a content-addressed manifest for scene evidence files."""

from __future__ import annotations

import argparse
import mimetypes
from pathlib import Path

from artifact_paths import ArtifactPathError, ArtifactPathResolver
from _core import ROOT, TOOL_VERSION, ChannelMakerError, content_hash, require_valid, sha256_file, slugify, write_json_atomic


KINDS = {"scene_json", "still", "contact_sheet", "video", "narration_timing", "audio", "validator_output", "source_packet"}


def parse_input(value: str) -> tuple[str, Path]:
    try:
        kind, raw_path = value.split("=", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("inputs must use KIND=PATH") from exc
    if kind not in KINDS:
        raise argparse.ArgumentTypeError(f"unknown evidence kind {kind!r}")
    path = Path(raw_path).expanduser().resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"evidence file does not exist: {path}")
    return kind, path


def build_candidate(
    scene_id: str,
    generator_agent: str,
    model: str,
    prompt_version: str,
    inputs: list[tuple[str, Path]],
    *,
    model_version: str | None = None,
    benchmark_case_id: str | None = None,
    repository_root: Path | None = None,
) -> dict:
    scene_id = slugify(scene_id)
    resolver = ArtifactPathResolver(repository_root or Path(__file__).resolve().parents[1])
    artifacts = []
    for index, (kind, path) in enumerate(inputs, start=1):
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        try:
            location = resolver.portable_location(path)
        except ArtifactPathError as exc:
            raise ChannelMakerError(str(exc)) from exc
        artifacts.append({
            "evidence_id": f"evidence-{index:03d}",
            "kind": kind,
            "location": location,
            "sha256": sha256_file(path),
            "media_type": media_type,
        })
    generator = {"agent": generator_agent, "model": model, "prompt_version": prompt_version}
    if model_version:
        generator["model_version"] = model_version
    payload = {"scene_id": scene_id, "generator": generator, "artifacts": artifacts}
    record = {
        "schema_version": "1.1.0",
        "artifact_type": "scene_candidate_manifest",
        "artifact_id": f"scene-candidate:{scene_id}:{content_hash(payload)[:12]}",
        "lifecycle_state": "complete",
        **payload,
        "created_by": {"tool": "radicat.build_scene_candidate", "version": TOOL_VERSION},
    }
    if benchmark_case_id:
        record["benchmark_case_id"] = slugify(benchmark_case_id)
    require_valid(record, label="scene candidate manifest")
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root used to resolve evidence locations.")
    parser.add_argument("--scene-id", required=True)
    parser.add_argument("--generator-agent", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-version")
    parser.add_argument("--prompt-version", required=True)
    parser.add_argument("--benchmark-case-id")
    parser.add_argument("--input", action="append", type=parse_input, required=True, help="KIND=PATH; repeat as needed")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        record = build_candidate(
            args.scene_id, args.generator_agent, args.model, args.prompt_version, args.input,
            model_version=args.model_version, benchmark_case_id=args.benchmark_case_id,
            repository_root=args.root,
        )
        write_json_atomic(args.output, record)
    except ChannelMakerError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
