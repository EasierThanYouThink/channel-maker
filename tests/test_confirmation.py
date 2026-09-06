from __future__ import annotations

import argparse
import builtins
from pathlib import Path

import pilot as pilot_cli
import pytest
from _confirmation import require_confirmation


class ConfirmationError(RuntimeError):
    pass


def test_confirmation_treats_eof_as_non_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("_confirmation.sys.stdin.isatty", lambda: True)

    def end_of_input(_prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr(builtins, "input", end_of_input)

    with pytest.raises(ConfirmationError, match="requires --yes"):
        require_confirmation(
            assume_yes=False,
            prompt="Type yes: ",
            error_type=ConfirmationError,
            noninteractive_message="this action requires --yes",
            cancelled_message="action cancelled",
        )


def test_confirmation_assume_yes_never_reads_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_call(*_args: object, **_kwargs: object) -> bool:
        raise AssertionError("stdin must not be inspected with --yes")

    monkeypatch.setattr("_confirmation.sys.stdin.isatty", unexpected_call)
    monkeypatch.setattr(builtins, "input", unexpected_call)

    require_confirmation(
        assume_yes=True,
        prompt="Type yes: ",
        error_type=ConfirmationError,
        noninteractive_message="this action requires --yes",
        cancelled_message="action cancelled",
    )


def test_confirmation_rejects_interactive_non_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("_confirmation.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(builtins, "input", lambda _prompt: "no")

    with pytest.raises(ConfirmationError, match="action cancelled"):
        require_confirmation(
            assume_yes=False,
            prompt="Type yes: ",
            error_type=ConfirmationError,
            noninteractive_message="this action requires --yes",
            cancelled_message="action cancelled",
        )


def test_pilot_cli_reports_eof_as_requires_yes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    args = argparse.Namespace(
        command="record-review",
        yes=False,
        decision="GO",
        pilot_id="pilot-1",
        package_root=tmp_path / "unused",
        root=tmp_path,
    )
    monkeypatch.setattr(pilot_cli, "parse_args", lambda: args)
    monkeypatch.setattr("_confirmation.sys.stdin.isatty", lambda: True)

    def end_of_input(_prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr(builtins, "input", end_of_input)

    assert pilot_cli.main() == 2
    assert "requires --yes" in capsys.readouterr().out
