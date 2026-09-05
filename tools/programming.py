#!/usr/bin/env python3
"""Programming desk: hypotheses, assignments, costs, outcomes, slates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.programming import (  # noqa: E402
    ProgrammingError,
    approve_slate,
    assign_episode,
    list_hypotheses,
    list_slates,
    propose_hypothesis,
    propose_slate,
    record_cost,
    record_outcome,
    record_publication,
)
from engine.programming.store import init_desk  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("package_root", type=Path)

    propose = commands.add_parser("propose-hypothesis")
    propose.add_argument("package_root", type=Path)
    propose.add_argument("hypothesis_id")
    propose.add_argument("--statement", required=True)
    propose.add_argument("--opportunity-ref", default=None)
    propose.add_argument("--group", default="explore", choices=["explore", "proven", "control"])

    assign = commands.add_parser("assign")
    assign.add_argument("package_root", type=Path)
    assign.add_argument("episode_id")
    assign.add_argument("--hypothesis", required=True)

    cost = commands.add_parser("cost")
    cost.add_argument("package_root", type=Path)
    cost.add_argument("episode_id")
    cost.add_argument("--minutes", type=float, required=True)
    cost.add_argument("--notes", default="")

    publish = commands.add_parser("publish")
    publish.add_argument("package_root", type=Path)
    publish.add_argument("episode_id")
    publish.add_argument("--receipt-ref", default=None)

    outcome = commands.add_parser("outcome")
    outcome.add_argument("package_root", type=Path)
    outcome.add_argument("episode_id")
    outcome.add_argument("--measurement", action="append", default=[], dest="measurements")
    outcome.add_argument("--provenance", required=True)
    outcome.add_argument("--window", required=True)

    slate = commands.add_parser("propose-slate")
    slate.add_argument("package_root", type=Path)
    slate.add_argument("slate_id")
    slate.add_argument("--episode", action="append", default=[], dest="episode_ids")
    slate.add_argument("--rationale", default="")

    approve = commands.add_parser("approve-slate")
    approve.add_argument("package_root", type=Path)
    approve.add_argument("slate_id")
    approve.add_argument("--approved-by", required=True)
    approve.add_argument("--decision-ref", required=True)
    approve.add_argument("--yes", action="store_true")

    show = commands.add_parser("list")
    show.add_argument("package_root", type=Path)
    return parser.parse_args()


def _measurements(values: list[str]) -> dict[str, str]:
    measurements: dict[str, str] = {}
    for value in values:
        try:
            name, measurement = value.split("=", 1)
        except ValueError as exc:
            raise ProgrammingError(f"measurements must use NAME=VALUE: {value!r}") from exc
        measurements[name.strip()] = measurement.strip()
    return measurements


def main() -> int:
    args = parse_args()
    try:
        if args.command == "init":
            print(init_desk(args.package_root, args.root))
        elif args.command == "propose-hypothesis":
            print(json.dumps(propose_hypothesis(
                args.package_root, args.root, hypothesis_id=args.hypothesis_id,
                statement=args.statement, opportunity_ref=args.opportunity_ref,
                comparison_group=args.group,
            ), indent=2, sort_keys=True))
        elif args.command == "assign":
            print(json.dumps(assign_episode(
                args.package_root, args.root, hypothesis_id=args.hypothesis,
                episode_id=args.episode_id,
            ), indent=2, sort_keys=True))
        elif args.command == "cost":
            print(json.dumps(record_cost(
                args.package_root, args.root, episode_id=args.episode_id,
                minutes=args.minutes, notes=args.notes,
            ), indent=2, sort_keys=True))
        elif args.command == "publish":
            print(json.dumps(record_publication(
                args.package_root, args.root, episode_id=args.episode_id,
                receipt_ref=args.receipt_ref,
            ), indent=2, sort_keys=True))
        elif args.command == "outcome":
            print(json.dumps(record_outcome(
                args.package_root, args.root, episode_id=args.episode_id,
                measurements=_measurements(args.measurements),
                provenance=args.provenance, window=args.window,
            ), indent=2, sort_keys=True))
        elif args.command == "propose-slate":
            print(json.dumps(propose_slate(
                args.package_root, args.root, slate_id=args.slate_id,
                episode_ids=args.episode_ids, rationale=args.rationale,
            ), indent=2, sort_keys=True))
        elif args.command == "approve-slate":
            if not args.yes and not sys.stdin.isatty():
                raise ProgrammingError("approving a slate requires --yes (non-interactive) or an interactive human terminal")
            if not args.yes and input("Approve this slate? Type yes: ").strip().lower() != "yes":
                raise ProgrammingError("slate approval cancelled")
            print(json.dumps(approve_slate(
                args.package_root, args.root, slate_id=args.slate_id,
                approved_by=args.approved_by, decision_ref=args.decision_ref,
                human_confirmed=True,
            ), indent=2, sort_keys=True))
        else:
            print(json.dumps({
                "hypotheses": list_hypotheses(args.package_root, args.root),
                "slates": list_slates(args.package_root, args.root),
            }, indent=2, sort_keys=True))
    except ProgrammingError as exc:
        print(f"PROGRAMMING ERROR\n- {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
