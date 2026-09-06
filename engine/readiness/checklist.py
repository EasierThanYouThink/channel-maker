"""Compute and (only if fully passing) persist a channel's CHANNEL_READY readiness report."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from engine.channel import ChannelValidationError, validate_channel_package
from engine.design import all_domains_frozen, seed_path
from engine.foundation.validation import FoundationValidationError, validate_foundation
from engine.identity import all_domains_frozen as identity_all_domains_frozen
from engine.identity import identity_path
from engine.library import list_components
from engine.pilot import PilotValidationError, pilot_path, validate_pilot
from engine.production import check_production, production_revision
from engine.script.validation import ScriptValidationError, validate_script_dna

CONTRACT_ROOT = Path(__file__).resolve().parent / "contracts"


class ReadinessError(ValueError):
    """A readiness report could not be computed or persisted."""


def _timestamp(value: str | None) -> str:
    return value or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write((json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _item(item_id: str, label: str, passed: bool, evidence_refs: list[str], explanation: str) -> dict[str, Any]:
    return {"item_id": item_id, "label": label, "passed": passed, "evidence_refs": evidence_refs, "explanation": explanation}


def _iter_pilots(package_root: Path) -> list[tuple[str, dict[str, Any]]]:
    pilots_root = package_root / "pilots"
    if not pilots_root.is_dir():
        return []
    results = []
    for pilot_dir in sorted(pilots_root.iterdir()):
        candidate = pilot_dir / "pilot.json"
        if candidate.is_file():
            results.append((pilot_dir.name, json.loads(candidate.read_text(encoding="utf-8"))))
    return results


def _find_reviewed_pilot(package_root: Path) -> tuple[str, dict[str, Any]] | None:
    return next((entry for entry in _iter_pilots(package_root) if entry[1]["review"]["decision"] is not None), None)


def _find_frozen_pilot(package_root: Path) -> tuple[str, dict[str, Any]] | None:
    return next((entry for entry in _iter_pilots(package_root) if entry[1]["freeze"]["frozen"]), None)


def check_readiness(package_root: Path, repository_root: Path) -> dict[str, Any]:
    """Compute the CHANNEL_READY readiness checklist. Never raises for a failing item."""

    repository_root = repository_root.resolve()
    try:
        package = validate_channel_package(package_root.resolve(), repository_root)
    except ChannelValidationError as exc:
        raise ReadinessError(str(exc)) from exc
    channel_id = package.identity["id"]
    root = package.root
    items: list[dict[str, Any]] = []

    # 1. Strategy selection recorded with an explicit human decision.
    strategy_event = next(
        (e for e in package.state["events"] if e["operation"] == "ADVANCE" and e["to_state"] == "STRATEGY_SELECTION"),
        None,
    )
    items.append(_item(
        "strategy_selected", "Strategy selection recorded with an explicit human decision",
        strategy_event is not None and bool(strategy_event.get("human_decision_ref")),
        [strategy_event["human_decision_ref"]] if strategy_event and strategy_event.get("human_decision_ref") else [],
        "No STRATEGY_SELECTION advance with a human_decision_ref was found in the channel's event log."
        if not (strategy_event and strategy_event.get("human_decision_ref")) else "Recorded.",
    ))

    # 2. Audience/promise (Channel Foundation) drafted with at least one attached decision.
    foundation_path = root / "strategy" / "foundation.yaml"
    foundation_ok = False
    if foundation_path.is_file():
        try:
            document = yaml.safe_load(foundation_path.read_text(encoding="utf-8"))
            validate_foundation(document, expected_channel_id=channel_id)
            foundation_ok = bool(document["decision_refs"])
        except (FoundationValidationError, yaml.YAMLError):
            foundation_ok = False
    items.append(_item(
        "audience_promise", "Channel Foundation (audience/promise) drafted and decision-attached",
        foundation_ok, [str(foundation_path.relative_to(repository_root))] if foundation_ok else [],
        "Channel Foundation is missing, invalid, or has no attached decision_refs." if not foundation_ok else "Recorded.",
    ))

    # 3. Script DNA frozen.
    script_dna_path = root / "script" / "script-dna.yaml"
    script_ok = False
    if script_dna_path.is_file():
        try:
            document = yaml.safe_load(script_dna_path.read_text(encoding="utf-8"))
            validate_script_dna(document, expected_channel_id=channel_id)
            script_ok = document["status"] == "FROZEN"
        except (ScriptValidationError, yaml.YAMLError):
            script_ok = False
    items.append(_item(
        "script_dna_frozen", "Script DNA frozen", script_ok,
        [str(script_dna_path.relative_to(repository_root))] if script_ok else [],
        "Script DNA is missing, invalid, or not yet frozen." if not script_ok else "Recorded.",
    ))

    # 4/5. Visual and Motion DNA: every domain frozen, plus the approved
    # system proof (composed frame for visual, narrated sample for motion).
    from engine.design import (
        approved_composition,
        approved_motion_sample,
        composition_path,
        motion_sample_path,
    )

    dna_results: dict[str, bool] = {}
    for kind in ("visual", "motion"):
        path = seed_path(kind, root)
        proof_ok = approved_composition(root) if kind == "visual" else approved_motion_sample(root)
        proof_path = composition_path(root) if kind == "visual" else motion_sample_path(root)
        ok = False
        if path.is_file():
            try:
                document = yaml.safe_load(path.read_text(encoding="utf-8"))
                ok = all_domains_frozen(kind, document) and proof_ok
            except yaml.YAMLError:
                ok = False
        dna_results[kind] = ok
        refs = [str(path.relative_to(repository_root))] if path.is_file() else []
        if proof_ok:
            refs.append(str(proof_path.relative_to(repository_root)))
        items.append(_item(
            f"{kind}_dna_frozen", f"{kind.title()} DNA: every domain frozen plus the approved system proof", ok,
            refs if ok else [],
            f"{kind.title()} DNA seed is missing, has an unfrozen domain, or lacks its approved system proof." if not ok else "Recorded.",
        ))

    # 5b. Channel Identity: logo and description both frozen.
    identity_seed_path = identity_path(root)
    identity_ok = False
    if identity_seed_path.is_file():
        try:
            document = yaml.safe_load(identity_seed_path.read_text(encoding="utf-8"))
            identity_ok = identity_all_domains_frozen(document)
        except yaml.YAMLError:
            identity_ok = False
    items.append(_item(
        "identity_frozen", "Channel Identity (logo, description): every domain frozen", identity_ok,
        [str(identity_seed_path.relative_to(repository_root))] if identity_ok else [],
        "Channel Identity seed is missing or has at least one unfrozen domain." if not identity_ok else "Recorded.",
    ))

    # 6. At least one approved design exemplar.
    exemplars_dir = root / "design" / "exemplars" / "records"
    approved_exemplars = []
    if exemplars_dir.is_dir():
        for candidate in sorted(exemplars_dir.glob("*.json")):
            record = json.loads(candidate.read_text(encoding="utf-8"))
            if record["classification"] == "approved":
                approved_exemplars.append(str(candidate.relative_to(repository_root)))
    items.append(_item(
        "approved_exemplar", "At least one approved design exemplar", bool(approved_exemplars),
        approved_exemplars, "No approved design exemplar was found." if not approved_exemplars else "Recorded.",
    ))

    # 7. At least one approved asset component — or an honest declaration
    # that the pilot needs none (scene-local construction, not a token part).
    approved_components = list(
        list_components(repository_root, scope="CHANNEL", channel_id=channel_id, status="approved")
    )
    waived = any(
        pilot.get("plan", {}).get("no_reusable_components") is True
        for _, pilot in _iter_pilots(root)
    )
    component_ok = bool(approved_components) or waived
    items.append(_item(
        "approved_component", "At least one approved asset component (or an honest no-component pilot plan)",
        component_ok,
        [c["component_id"] for c in approved_components] if approved_components else [],
        "No approved asset component was found for this channel." if not component_ok else "Recorded.",
    ))

    # 8. Validated workflow: every structured artifact produced so far re-validates cleanly.
    workflow_ok = all(item["passed"] for item in items)
    items.append(_item(
        "validated_workflow", "Every produced structured artifact validates", workflow_ok, [],
        "One or more earlier artifacts do not currently validate." if not workflow_ok else "Recorded.",
    ))

    # 9/10/11. Reviewed pilot, explicit human GO, persisted version.
    reviewed_pilot = _find_reviewed_pilot(root)
    frozen_pilot = _find_frozen_pilot(root)
    reviewed_ok = reviewed_pilot is not None
    items.append(_item(
        "reviewed_pilot", "At least one pilot has a recorded review decision", reviewed_ok,
        [f"channels/{channel_id}/pilots/{reviewed_pilot[0]}/pilot.json"] if reviewed_pilot else [],
        "No pilot with a recorded review decision was found." if not reviewed_ok else "Recorded.",
    ))

    # No circularity: this item must pass BEFORE the CHANNEL_READY advance
    # (the report is that advance's prerequisite), so it verifies the GO +
    # freeze evidence itself. The READY edge's own human gate then rechecks
    # the same decision ref at advance time.
    human_go_ok = False
    go_refs: list[str] = []
    try:
        pilot_id = frozen_pilot[0] if frozen_pilot else None
        if pilot_id:
            document = json.loads(pilot_path(root, pilot_id).read_text(encoding="utf-8"))
            validate_pilot(document, repository_root=repository_root, expected_channel_id=channel_id)
            current_rev = production_revision(document["production"], repository_root=repository_root)
            human_go_ok = (
                document["review"]["decision"] == "GO"
                and document["review"].get("rev_id") == current_rev
                and bool(document["review"].get("decision_ref"))
            )
            if human_go_ok:
                go_refs = [document["review"]["decision_ref"]]
    except (PilotValidationError, OSError, json.JSONDecodeError):
        human_go_ok = False
    items.append(_item(
        "explicit_human_go", "A frozen pilot carries an explicit human GO decision bound to the current production revision",
        human_go_ok, go_refs,
        "No frozen pilot with a GO review, the decision_ref is missing, "
        "or its production changed since the GO review."
        if not human_go_ok else "Recorded.",
    ))

    production_pilot = frozen_pilot or reviewed_pilot
    production_problems: list[str] = []
    production_refs: list[str] = []
    if production_pilot is not None:
        production_problems = check_production(
            production_pilot[1]["production"], repository_root=repository_root,
            label=f"pilot {production_pilot[0]}",
        )
        production_refs = [f"channels/{channel_id}/pilots/{production_pilot[0]}/pilot.json"]
    production_ok = production_pilot is not None and not production_problems
    items.append(_item(
        "complete_production", "The reviewed pilot is a real, exact production (script, narration, scenes, render)",
        production_ok, production_refs if production_ok else [],
        "; ".join(production_problems) if not production_ok else "Recorded.",
    ))

    persisted_ok = frozen_pilot is not None and frozen_pilot[1]["freeze"]["new_channel_version"] == package.identity["version"]
    items.append(_item(
        "persisted_version", "The channel's persisted version matches its frozen pilot", persisted_ok,
        [f"channels/{channel_id}/channel.yaml"] if persisted_ok else [],
        "The channel's persisted version does not match its frozen pilot's new_channel_version."
        if not persisted_ok else "Recorded.",
    ))

    overall_passed = all(item["passed"] for item in items)
    report = {
        "schema_version": "1.0.0", "artifact_type": "readiness_report", "channel_id": channel_id,
        "items": items, "overall_passed": overall_passed, "authority": "advisory_only",
        "created_by": {
            "created_at": _timestamp(None), "creator": "TOOL",
            "tool": "engine.readiness.checklist.check_readiness", "version": "1.0.0",
        },
    }
    return report


def write_readiness_report(package_root: Path, repository_root: Path) -> Path:
    """Write the readiness report ONLY if every checklist item passes."""

    report = check_readiness(package_root, repository_root)
    if not report["overall_passed"]:
        failed = [item["item_id"] for item in report["items"] if not item["passed"]]
        raise ReadinessError(f"channel is not ready; failing items: {failed}")

    schema = json.loads((CONTRACT_ROOT / "readiness-report.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = list(validator.iter_errors(report))
    if errors:
        raise ReadinessError("\n".join(error.message for error in errors))

    package_root = package_root.resolve() if package_root.is_absolute() else repository_root.resolve() / package_root
    path = package_root / "readiness-report.json"
    _write_json_atomic(path, report)
    return path
