from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .agent_profile import (
    ExecutionEnvironment,
    assert_child_profile_narrower,
    build_session_descriptor,
    load_profile,
)


def _print_json(value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str))


def _environment(value: str) -> ExecutionEnvironment:
    try:
        return ExecutionEnvironment(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("environment must be sandbox or live") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="valo-gateway",
        description="Validate and compile runtime-agnostic governed agent profiles.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    profile = commands.add_parser("profile", help="Governed agent profile operations")
    profile_commands = profile.add_subparsers(dest="profile_command", required=True)

    validate = profile_commands.add_parser("validate", help="Validate a profile")
    validate.add_argument("path", type=Path)

    show = profile_commands.add_parser("show", help="Print canonical profile JSON")
    show.add_argument("path", type=Path)

    tools = profile_commands.add_parser("tools", help="List governed tool handles")
    tools.add_argument("path", type=Path)
    tools.add_argument("--environment", type=_environment, default=ExecutionEnvironment.SANDBOX)

    compile_command = profile_commands.add_parser(
        "compile",
        help="Compile a secret-free profile bundle for any runtime or harness",
    )
    compile_command.add_argument("path", type=Path)
    compile_command.add_argument("--runtime-id", required=True)
    compile_command.add_argument("--environment", type=_environment)

    session = profile_commands.add_parser(
        "session-descriptor",
        help="Create a non-secret delegated-session descriptor",
    )
    session.add_argument("path", type=Path)
    session.add_argument("--runtime-id", required=True)
    session.add_argument("--environment", type=_environment)
    session.add_argument("--ttl-seconds", type=int)

    compare = profile_commands.add_parser(
        "compare-parent",
        help="Prove that a child profile only narrows its parent",
    )
    compare.add_argument("parent", type=Path)
    compare.add_argument("child", type=Path)

    fingerprint = profile_commands.add_parser("fingerprint", help="Print profile digest")
    fingerprint.add_argument("path", type=Path)
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.profile_command == "validate":
        profile = load_profile(args.path)
        _print_json(
            {
                "valid": True,
                "profile_id": profile.profile_id,
                "profile_digest": profile.digest,
                "authorization_boundary": "REHT",
                "runtime_agnostic": True,
            }
        )
        return 0

    if args.profile_command == "show":
        _print_json(load_profile(args.path))
        return 0

    if args.profile_command == "tools":
        profile = load_profile(args.path)
        _print_json(profile.tools_for(args.environment))
        return 0

    if args.profile_command == "compile":
        profile = load_profile(args.path)
        compiled = profile.compile_for_runtime(
            runtime_id=args.runtime_id,
            environment=args.environment,
        )
        _print_json(compiled)
        return 0

    if args.profile_command == "session-descriptor":
        profile = load_profile(args.path)
        compiled = profile.compile_for_runtime(
            runtime_id=args.runtime_id,
            environment=args.environment,
        )
        _print_json(
            build_session_descriptor(
                compiled,
                ttl_seconds=args.ttl_seconds,
            )
        )
        return 0

    if args.profile_command == "compare-parent":
        parent = load_profile(args.parent)
        child = load_profile(args.child)
        assert_child_profile_narrower(parent=parent, child=child)
        _print_json(
            {
                "valid": True,
                "parent_profile_id": parent.profile_id,
                "child_profile_id": child.profile_id,
                "relationship": "narrower_or_equal",
            }
        )
        return 0

    if args.profile_command == "fingerprint":
        print(load_profile(args.path).digest)
        return 0

    raise RuntimeError(f"unsupported command: {args.profile_command}")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
