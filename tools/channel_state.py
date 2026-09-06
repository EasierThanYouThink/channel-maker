#!/usr/bin/env python3
"""Inspect and mutate a Channel Package through the CM1 workflow runtime."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from _confirmation import require_confirmation  # noqa: E402

from engine.channel import ChannelStateError, ChannelStateMachine  # noqa: E402


def _package(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("package", type=Path)


def _mutation(parser: argparse.ArgumentParser) -> None:
    _package(parser)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--at", dest="occurred_at")
    parser.add_argument("--expected-revision", type=int)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)

    show = commands.add_parser("show")
    _package(show)
    next_action = commands.add_parser("next")
    _package(next_action)

    validate = commands.add_parser("validate-transition")
    _package(validate)
    validate.add_argument("target")
    validate.add_argument("--prerequisite-ref", action="append", default=[])
    validate.add_argument("--human-decision-ref")

    advance = commands.add_parser("advance")
    _mutation(advance)
    advance.add_argument("target")
    advance.add_argument("--next-action", required=True)
    advance.add_argument("--reason", required=True)
    advance.add_argument("--prerequisite-ref", action="append", default=[])
    advance.add_argument("--human-decision-ref")

    block = commands.add_parser("block")
    _mutation(block)
    block.add_argument("--reason-code", required=True)
    block.add_argument("--summary", required=True)
    block.add_argument("--question", required=True)
    block.add_argument("--required-action", required=True)

    resume = commands.add_parser("resume")
    _mutation(resume)
    resume.add_argument("--human-response-ref", required=True)
    resume.add_argument("--next-action", required=True)

    revise = commands.add_parser("revise")
    _mutation(revise)
    revise.add_argument("target")
    revise.add_argument("--decision-ref", required=True)
    revise.add_argument("--next-action", required=True)
    revise.add_argument("--reason", required=True)
    revise.add_argument("--yes", action="store_true")

    abandon = commands.add_parser("abandon")
    _mutation(abandon)
    abandon.add_argument("--decision-ref", required=True)
    abandon.add_argument("--reason", required=True)
    abandon.add_argument("--yes", action="store_true")
    return parser.parse_args()


def _require_human_confirm(args: argparse.Namespace, what: str) -> None:
    require_confirmation(
        assume_yes=args.yes,
        prompt=f"Record human channel {what}? Type yes: ",
        error_type=ChannelStateError,
        noninteractive_message=(
            f"channel {what} requires --yes (non-interactive) or an interactive human terminal"
        ),
        cancelled_message=f"human channel {what} cancelled",
    )


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    package = args.package if args.package.is_absolute() else root / args.package
    runtime = ChannelStateMachine(package, root)
    mutation = {
        "actor": getattr(args, "actor", None),
        "occurred_at": getattr(args, "occurred_at", None),
        "expected_revision": getattr(args, "expected_revision", None),
    }
    try:
        if args.command == "show":
            result = runtime.show()
        elif args.command == "next":
            result = asdict(runtime.next_allowed_action())
        elif args.command == "validate-transition":
            result = runtime.validate_transition(
                args.target,
                prerequisite_refs=args.prerequisite_ref,
                human_decision_ref=args.human_decision_ref,
            )
        elif args.command == "advance":
            result = runtime.advance(
                args.target,
                next_action=args.next_action,
                reason=args.reason,
                prerequisite_refs=args.prerequisite_ref,
                human_decision_ref=args.human_decision_ref,
                **mutation,
            )
        elif args.command == "block":
            result = runtime.block_on_human(
                reason_code=args.reason_code,
                summary=args.summary,
                question=args.question,
                required_action=args.required_action,
                **mutation,
            )
        elif args.command == "resume":
            result = runtime.resume(
                human_response_ref=args.human_response_ref,
                next_action=args.next_action,
                **mutation,
            )
        elif args.command == "revise":
            _require_human_confirm(args, f"revise to {args.target}")
            result = runtime.revise(
                args.target,
                decision_ref=args.decision_ref,
                next_action=args.next_action,
                reason=args.reason,
                **mutation,
            )
        else:
            _require_human_confirm(args, "abandon")
            result = runtime.abandon(
                decision_ref=args.decision_ref,
                reason=args.reason,
                **mutation,
            )
    except ChannelStateError as exc:
        print(f"CHANNEL STATE ERROR\n- {exc}")
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
