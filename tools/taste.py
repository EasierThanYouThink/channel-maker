#!/usr/bin/env python3
"""Taste compiler: compare productions, propose policies, promote on held-out proof."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from _confirmation import require_confirmation  # noqa: E402

from engine.taste import (  # noqa: E402
    TasteError,
    list_comparisons,
    list_policies,
    promote_policy,
    propose_policy,
    record_comparison,
    retire_policy,
)
from engine.taste.store import init_taste  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("package_root", type=Path)

    compare = commands.add_parser("compare")
    compare.add_argument("package_root", type=Path)
    compare.add_argument("--preferred-ref", required=True)
    compare.add_argument("--rejected-ref", required=True)
    compare.add_argument("--reason", required=True)
    compare.add_argument("--decided-by", required=True)
    compare.add_argument("--decision-ref", required=True)
    compare.add_argument("--context", default="")

    propose = commands.add_parser("propose")
    propose.add_argument("package_root", type=Path)
    propose.add_argument("--statement", required=True)
    propose.add_argument("--scope", required=True)
    propose.add_argument("--comparison", action="append", default=[], dest="comparison_ids")
    propose.add_argument("--uncertainty", default="")

    promote = commands.add_parser("promote")
    promote.add_argument("package_root", type=Path)
    promote.add_argument("policy_id")
    promote.add_argument("--promoted-by", required=True)
    promote.add_argument("--decision-ref", required=True)
    promote.add_argument("--heldout-ref", required=True)
    promote.add_argument("--yes", action="store_true")

    retire = commands.add_parser("retire")
    retire.add_argument("package_root", type=Path)
    retire.add_argument("policy_id")
    retire.add_argument("--reason", required=True)

    show = commands.add_parser("list")
    show.add_argument("package_root", type=Path)
    show.add_argument("--status", default=None, choices=["proposed", "promoted", "retired"])
    return parser.parse_args()


def _require_human_confirm(args: argparse.Namespace) -> None:
    require_confirmation(
        assume_yes=args.yes,
        prompt="Promote this taste policy to guidance? Type yes: ",
        error_type=TasteError,
        noninteractive_message=(
            "promoting a taste policy requires --yes (non-interactive) or an interactive human terminal"
        ),
        cancelled_message="taste promotion cancelled",
    )


def main() -> int:
    args = parse_args()
    try:
        if args.command == "init":
            print(init_taste(args.package_root, args.root))
        elif args.command == "compare":
            print(json.dumps(record_comparison(
                args.package_root, args.root, preferred_ref=args.preferred_ref,
                rejected_ref=args.rejected_ref, reason=args.reason,
                decided_by=args.decided_by, decision_ref=args.decision_ref,
                context=args.context,
            ), indent=2, sort_keys=True))
        elif args.command == "propose":
            print(json.dumps(propose_policy(
                args.package_root, args.root, statement=args.statement, scope=args.scope,
                comparison_ids=args.comparison_ids, uncertainty=args.uncertainty,
            ), indent=2, sort_keys=True))
        elif args.command == "promote":
            _require_human_confirm(args)
            print(json.dumps(promote_policy(
                args.package_root, args.root, policy_id=args.policy_id,
                promoted_by=args.promoted_by, decision_ref=args.decision_ref,
                heldout_ref=args.heldout_ref, human_confirmed=True,
            ), indent=2, sort_keys=True))
        elif args.command == "retire":
            print(json.dumps(retire_policy(
                args.package_root, args.root, policy_id=args.policy_id, reason=args.reason,
            ), indent=2, sort_keys=True))
        else:
            print(json.dumps({
                "comparisons": list_comparisons(args.package_root, args.root),
                "policies": list_policies(args.package_root, args.root, status=args.status),
            }, indent=2, sort_keys=True))
    except TasteError as exc:
        print(f"TASTE ERROR\n- {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
