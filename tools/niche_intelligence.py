"""Validate and query offline CM3 Niche Intelligence artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.niche_intelligence import (
    MetricError,
    NicheIntelligenceRepository,
    NicheValidationError,
    add_content_annotation,
    add_hypothesis,
    add_observation,
    add_opportunity,
    add_script_annotation,
    add_visual_market_annotation,
    import_evidence,
    relative_views_same_channel_v1,
    study_coverage,
    validate_contracts,
    validate_study,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root used to resolve canonical study paths.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate-contracts")
    validate = subparsers.add_parser("validate")
    validate.add_argument("study_root", type=Path)
    coverage = subparsers.add_parser("coverage", help="Report what a study covers — and what it leaves out")
    coverage.add_argument("study_root", type=Path)
    metric = subparsers.add_parser("relative-views")
    metric.add_argument("request_json", type=Path, help="JSON object matching metric function arguments")
    context = subparsers.add_parser("context")
    context.add_argument("package_root", type=Path)
    context.add_argument("study_root", type=Path)
    context.add_argument("query")
    context.add_argument("--include-engine", action="store_true")
    publish = subparsers.add_parser("publish-summaries")
    publish.add_argument("package_root", type=Path)
    publish.add_argument("study_root", type=Path)

    import_ev = subparsers.add_parser("import-evidence", help="Import a reviewed Hermes collection response into CM3 evidence")
    import_ev.add_argument("study_root", type=Path)
    import_ev.add_argument("response_json", type=Path)
    import_ev.add_argument("--reviewed-by", required=True)
    import_ev.add_argument("--reviewed-at")

    add_obs = subparsers.add_parser("add-observation")
    add_obs.add_argument("study_root", type=Path)
    add_obs.add_argument("--key", required=True)
    add_obs.add_argument("--statement", required=True)
    add_obs.add_argument("--observation-type", required=True, choices=[
        "PERFORMANCE_PATTERN", "CONTENT_PATTERN", "SCRIPT_PATTERN", "VISUAL_MARKET_PATTERN",
        "AUDIENCE_SIGNAL_PATTERN", "MARKET_GAP", "OTHER",
    ])
    add_obs.add_argument("--scope", required=True)
    add_obs.add_argument("--basis", required=True, choices=["PUBLIC_FACT", "DERIVED_MEASUREMENT", "ANNOTATION", "MIXED"])
    add_obs.add_argument("--evidence-ref", action="append", required=True, dest="evidence_refs")
    add_obs.add_argument("--confidence", type=float, default=None)
    add_obs.add_argument("--limitation", action="append", required=True, dest="limitations")

    add_hyp = subparsers.add_parser("add-hypothesis")
    add_hyp.add_argument("study_root", type=Path)
    add_hyp.add_argument("--key", required=True)
    add_hyp.add_argument("--statement", required=True)
    add_hyp.add_argument("--predicted-effect", required=True)
    add_hyp.add_argument("--applicable-context", required=True)
    add_hyp.add_argument("--observation-ref", action="append", required=True, dest="observation_refs")
    add_hyp.add_argument("--competing-explanation", action="append", required=True, dest="competing_explanations")
    add_hyp.add_argument("--confidence", type=float, default=None)
    add_hyp.add_argument("--test-idea", default=None)

    add_opp = subparsers.add_parser("add-opportunity")
    add_opp.add_argument("study_root", type=Path)
    add_opp.add_argument("--key", required=True)
    add_opp.add_argument("--observed-market", required=True)
    add_opp.add_argument("--underrepresented", required=True)
    add_opp.add_argument("--proposal", required=True)
    add_opp.add_argument("--hypothesis-ref", action="append", required=True, dest="hypothesis_refs")
    add_opp.add_argument("--evidence-ref", action="append", required=True, dest="evidence_refs")
    add_opp.add_argument("--risk", action="append", required=True, dest="risks")
    add_opp.add_argument("--confidence", type=float, default=None)

    content_ann = subparsers.add_parser(
        "add-teardown-content",
        help="Record a what-works content teardown of one video (hook family, structure, characteristics, ending)",
    )
    content_ann.add_argument("study_root", type=Path)
    content_ann.add_argument("--key", required=True)
    content_ann.add_argument("--video-evidence-id", required=True)
    content_ann.add_argument(
        "--payload-json", type=Path, required=True,
        help="JSON file with the content-annotation 'annotation' object (primary_topic, hook_family, structure, ...)",
    )
    content_ann.add_argument("--confidence", type=float, default=None)

    script_ann = subparsers.add_parser(
        "add-teardown-script",
        help="Record a what-works script teardown of one video (transcript provenance, statistics, hook/structure judgments)",
    )
    script_ann.add_argument("study_root", type=Path)
    script_ann.add_argument("--key", required=True)
    script_ann.add_argument("--video-evidence-id", required=True)
    script_ann.add_argument(
        "--payload-json", type=Path, required=True,
        help="JSON file with 'transcript', 'statistics', and 'annotations' objects per the script-annotation schema",
    )
    script_ann.add_argument("--confidence", type=float, default=None)

    visual_ann = subparsers.add_parser(
        "add-teardown-visual",
        help="Record a what-works visual teardown of one video (production approaches, pacing/text proxies, continuity). Market evidence only — never design authority.",
    )
    visual_ann.add_argument("study_root", type=Path)
    visual_ann.add_argument("--key", required=True)
    visual_ann.add_argument("--video-evidence-id", required=True)
    visual_ann.add_argument(
        "--payload-json", type=Path, required=True,
        help="JSON file with the visual-market-annotation 'annotation' object (production_approaches, ...)",
    )
    visual_ann.add_argument("--confidence", type=float, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "validate-contracts":
            print(f"NICHE INTELLIGENCE CONTRACTS VALID ({validate_contracts()})")
        elif args.command == "validate":
            study = validate_study(args.study_root)
            print(json.dumps({
                "channel_id": study.study["channel_id"], "study_id": study.study["study_id"],
                "study_version": study.study["study_version"], "artifact_count": len(study.artifacts),
            }, indent=2, sort_keys=True))
        elif args.command == "coverage":
            study = validate_study(args.study_root)
            print(json.dumps(study_coverage(study), indent=2, sort_keys=True))
        elif args.command == "relative-views":
            request = json.loads(args.request_json.read_text(encoding="utf-8"))
            if not isinstance(request, dict):
                raise NicheValidationError("metric request must be a JSON object")
            print(json.dumps(relative_views_same_channel_v1(**request), indent=2, sort_keys=True))
        elif args.command == "context":
            repository = NicheIntelligenceRepository(args.root.resolve())
            print(json.dumps(repository.build_context_bundle(
                args.package_root, args.study_root, args.query, include_engine=args.include_engine,
            ), indent=2, sort_keys=True))
        elif args.command == "publish-summaries":
            repository = NicheIntelligenceRepository(args.root.resolve())
            created = repository.publish_semantic_summaries(args.package_root, args.study_root)
            print(json.dumps([path.relative_to(args.root.resolve()).as_posix() for path in created], indent=2))
        elif args.command == "import-evidence":
            created = import_evidence(
                args.study_root, args.response_json, reviewed_by=args.reviewed_by,
                repository_root=args.root, reviewed_at=args.reviewed_at,
            )
            print(json.dumps([path.relative_to(args.root.resolve()).as_posix() for path in created], indent=2))
        elif args.command == "add-observation":
            path = add_observation(
                args.study_root, key=args.key, statement=args.statement,
                observation_type=args.observation_type, scope=args.scope, basis=args.basis,
                evidence_refs=args.evidence_refs, confidence=args.confidence,
                limitations=args.limitations, repository_root=args.root,
            )
            print(path.relative_to(args.root.resolve()).as_posix())
        elif args.command == "add-hypothesis":
            path = add_hypothesis(
                args.study_root, key=args.key, statement=args.statement,
                predicted_effect=args.predicted_effect, applicable_context=args.applicable_context,
                observation_refs=args.observation_refs, competing_explanations=args.competing_explanations,
                confidence=args.confidence, test_idea=args.test_idea, repository_root=args.root,
            )
            print(path.relative_to(args.root.resolve()).as_posix())
        elif args.command == "add-opportunity":
            path = add_opportunity(
                args.study_root, key=args.key, observed_market=args.observed_market,
                underrepresented=args.underrepresented, proposal=args.proposal,
                hypothesis_refs=args.hypothesis_refs, evidence_refs=args.evidence_refs,
                risks=args.risks, confidence=args.confidence, repository_root=args.root,
            )
            print(path.relative_to(args.root.resolve()).as_posix())
        elif args.command == "add-teardown-content":
            payload = _load_payload(args.payload_json, "annotation")
            path = add_content_annotation(
                args.study_root, key=args.key, video_evidence_id=args.video_evidence_id,
                annotation=payload["annotation"], confidence=args.confidence,
                repository_root=args.root,
            )
            print(path.relative_to(args.root.resolve()).as_posix())
        elif args.command == "add-teardown-script":
            payload = _load_payload(args.payload_json, "transcript", "statistics", "annotations")
            path = add_script_annotation(
                args.study_root, key=args.key, video_evidence_id=args.video_evidence_id,
                transcript=payload["transcript"], statistics=payload["statistics"],
                annotations=payload["annotations"], confidence=args.confidence,
                repository_root=args.root,
            )
            print(path.relative_to(args.root.resolve()).as_posix())
        else:
            payload = _load_payload(args.payload_json, "annotation")
            path = add_visual_market_annotation(
                args.study_root, key=args.key, video_evidence_id=args.video_evidence_id,
                annotation=payload["annotation"], confidence=args.confidence,
                repository_root=args.root,
            )
            print(path.relative_to(args.root.resolve()).as_posix())
    except (OSError, json.JSONDecodeError, MetricError, NicheValidationError) as exc:
        print(f"NICHE INTELLIGENCE ERROR\n{exc}")
        return 2
    return 0


def _load_payload(path: Path, *required_keys: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NicheValidationError(f"cannot read teardown payload {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise NicheValidationError(f"teardown payload {path} must be a JSON object")
    missing = [key for key in required_keys if key not in payload]
    if missing:
        raise NicheValidationError(f"teardown payload {path} is missing keys: {missing}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
