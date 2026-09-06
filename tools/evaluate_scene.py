"""Deterministically score a critic assessment under a human-owned contract."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from _core import (
    ROOT,
    TOOL_VERSION,
    ChannelMakerError,
    content_hash,
    load_json,
    require_valid,
    sha256_file,
    write_json_atomic,
)
from artifact_paths import ArtifactPathError, ArtifactPathResolver

FACTORS = {"pass": 1.0, "partial": 0.5, "fail": 0.0, "not_assessable": 0.0}


def _by_id(items: list[dict[str, Any]], field: str, label: str) -> dict[str, dict[str, Any]]:
    result = {item[field]: item for item in items}
    if len(result) != len(items):
        raise ChannelMakerError(f"duplicate {label} identifiers")
    return result


def evaluate(
    candidate_path: Path,
    contract_path: Path,
    assessment_path: Path,
    *,
    repository_root: Path | None = None,
) -> dict:
    candidate, contract, assessment = map(load_json, (candidate_path, contract_path, assessment_path))
    for record, label, artifact_type in (
        (candidate, "scene candidate", "scene_candidate_manifest"),
        (contract, "evaluation contract", "evaluation_contract"),
        (assessment, "critic assessment", "critic_assessment"),
    ):
        require_valid(record, label=label)
        if record["artifact_type"] != artifact_type:
            raise ChannelMakerError(f"{label} has unexpected artifact_type")
    if assessment["candidate_artifact_id"] != candidate["artifact_id"]:
        raise ChannelMakerError("assessment candidate_artifact_id does not match candidate")
    if assessment["contract_artifact_id"] != contract["artifact_id"]:
        raise ChannelMakerError("assessment contract_artifact_id does not match contract")
    if contract["scope"] == "scene_specific" and contract["scene_id"] != candidate["scene_id"]:
        raise ChannelMakerError("scene-specific contract does not match candidate scene_id")

    candidate_resolved = candidate_path.resolve()
    if repository_root is None:
        repository_root = ROOT if candidate_resolved.is_relative_to(ROOT) else candidate_resolved.parent
    resolver = ArtifactPathResolver(repository_root)
    for evidence in candidate["artifacts"]:
        location = evidence.get("location", evidence.get("path"))
        try:
            evidence_path = resolver.resolve(location).path
        except ArtifactPathError as exc:
            raise ChannelMakerError(f"candidate evidence {evidence['evidence_id']} is unavailable: {exc}") from exc
        if sha256_file(evidence_path) != evidence["sha256"]:
            raise ChannelMakerError(f"candidate evidence {evidence['evidence_id']} hash has changed")

    evidence_by_id = _by_id(candidate["artifacts"], "evidence_id", "candidate evidence")
    requirement_findings = _by_id(assessment["requirement_findings"], "requirement_id", "requirement finding")
    gate_findings = _by_id(assessment["gate_findings"], "gate_id", "gate finding")
    contract_requirement_ids = {
        requirement["requirement_id"] for dimension in contract["dimensions"] for requirement in dimension["requirements"]
    }
    contract_gate_ids = {gate["gate_id"] for gate in contract["hard_gates"]}
    if set(requirement_findings) != contract_requirement_ids:
        missing = sorted(contract_requirement_ids - set(requirement_findings))
        unknown = sorted(set(requirement_findings) - contract_requirement_ids)
        raise ChannelMakerError(f"requirement finding coverage mismatch; missing={missing}, unknown={unknown}")
    if set(gate_findings) != contract_gate_ids:
        missing = sorted(contract_gate_ids - set(gate_findings))
        unknown = sorted(set(gate_findings) - contract_gate_ids)
        raise ChannelMakerError(f"gate finding coverage mismatch; missing={missing}, unknown={unknown}")

    def check_evidence(finding: dict[str, Any], required_kinds: list[str], finding_id: str) -> None:
        cited_kinds = set()
        for citation in finding["evidence"]:
            evidence = evidence_by_id.get(citation["candidate_evidence_id"])
            if not evidence:
                raise ChannelMakerError(f"finding {finding_id} cites unknown candidate evidence")
            cited_kinds.add(evidence["kind"])
        if finding["outcome"] != "not_assessable":
            missing = set(required_kinds) - cited_kinds
            if missing:
                raise ChannelMakerError(f"finding {finding_id} lacks required evidence kinds: {sorted(missing)}")

    assessor_kind = assessment["assessor"]["kind"]
    allowed_requirement_assessors = {
        "critic": {"ai_critic", "human_reviewer"},
        "deterministic": {"deterministic_validator", "human_reviewer"},
        "human": {"human_reviewer"},
    }
    dimension_scores = []
    any_unassessable = False
    for dimension in contract["dimensions"]:
        awarded = 0.0
        scored_requirements = []
        for requirement in dimension["requirements"]:
            finding = requirement_findings[requirement["requirement_id"]]
            if assessor_kind not in allowed_requirement_assessors[requirement["assessment_method"]]:
                raise ChannelMakerError(
                    f"assessor kind {assessor_kind!r} cannot decide requirement {requirement['requirement_id']}"
                )
            check_evidence(finding, requirement["required_evidence_kinds"], requirement["requirement_id"])
            points = round(requirement["points"] * FACTORS[finding["outcome"]], 3)
            awarded += points
            any_unassessable |= finding["outcome"] == "not_assessable"
            scored_requirements.append({
                "requirement_id": requirement["requirement_id"], "possible_points": requirement["points"],
                "awarded_points": points, "outcome": finding["outcome"], "rationale": finding["rationale"],
            })
        dimension_scores.append({
            "dimension_id": dimension["dimension_id"], "possible_points": dimension["points"],
            "awarded_points": round(awarded, 3), "requirements": scored_requirements,
        })

    hard_gate_results = []
    gate_failed = False
    gate_unassessable = False
    for gate in contract["hard_gates"]:
        finding = gate_findings[gate["gate_id"]]
        if assessor_kind not in gate["allowed_assessors"]:
            raise ChannelMakerError(f"assessor kind {assessor_kind!r} cannot decide gate {gate['gate_id']}")
        if finding["outcome"] == "partial":
            raise ChannelMakerError(f"hard gate {gate['gate_id']} cannot have partial outcome")
        check_evidence(finding, gate["required_evidence_kinds"], gate["gate_id"])
        gate_failed |= finding["outcome"] == "fail"
        gate_unassessable |= finding["outcome"] == "not_assessable"
        hard_gate_results.append({"gate_id": gate["gate_id"], "outcome": finding["outcome"], "rationale": finding["rationale"]})

    score = round(sum(item["awarded_points"] for item in dimension_scores), 3)
    if gate_failed:
        recommendation = "blocked"
    elif gate_unassessable or any_unassessable:
        recommendation = "incomplete"
    elif score >= contract["thresholds"]["pass"]:
        recommendation = "passed"
    elif score >= contract["thresholds"]["needs_revision"]:
        recommendation = "needs_revision"
    else:
        recommendation = "failed"
    payload = {
        "candidate_artifact_id": candidate["artifact_id"], "candidate_sha256": sha256_file(candidate_path),
        "contract_artifact_id": contract["artifact_id"], "contract_sha256": sha256_file(contract_path),
        "assessment_artifact_id": assessment["artifact_id"], "assessment_sha256": sha256_file(assessment_path),
        "score_100": score, "dimension_scores": dimension_scores, "hard_gate_results": hard_gate_results,
        "machine_recommendation": recommendation, "authority": "advisory_only",
    }
    result = {
        "schema_version": "1.0.0", "artifact_type": "evaluation_result",
        "artifact_id": f"evaluation-result:{content_hash(payload)[:20]}", "lifecycle_state": "complete", **payload,
        "created_by": {"tool": "radicat.evaluate_scene", "version": TOOL_VERSION, "scoring_policy": "pass=1.0;partial=0.5;fail=0;not_assessable=0"},
    }
    require_valid(result, label="evaluation result")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root used to resolve candidate evidence locations.")
    parser.add_argument("candidate", type=Path)
    parser.add_argument("contract", type=Path)
    parser.add_argument("assessment", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        write_json_atomic(args.output, evaluate(args.candidate, args.contract, args.assessment, repository_root=args.root))
    except ChannelMakerError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
