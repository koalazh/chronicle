from __future__ import annotations

import argparse
import json
import sys

import uvicorn

from .app import create_app
from .config import load_config
from .doctor import doctor
from .hermes import bootstrap
from .scenario import validate_scenario, validate_source_pack


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chronicle", description="Chronicle: 甲申 command line")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("version")
    source = sub.add_parser("source")
    source.add_subparsers(dest="source_command").add_parser("validate")
    scenario = sub.add_parser("scenario")
    scenario.add_subparsers(dest="scenario_command").add_parser("validate")
    sub.add_parser("doctor")
    bootstrap_parser = sub.add_parser("bootstrap")
    bootstrap_parser.add_argument("--force-reset", action="store_true")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = load_config()
    try:
        if args.command == "version":
            print("Chronicle: 甲申 0.1.0")
        elif args.command == "source" and args.source_command == "validate":
            print("\n".join(validate_source_pack(config.scenario_path)))
        elif args.command == "scenario" and args.scenario_command == "validate":
            print("\n".join(validate_scenario(config.scenario_path)))
        elif args.command == "doctor":
            result = doctor(config)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] == "READY" else 1
        elif args.command == "bootstrap":
            result = bootstrap(config, force_reset=args.force_reset)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("ready") else 1
        elif args.command == "serve":
            uvicorn.run(create_app(config), host=args.host or config.host, port=args.port or config.port, reload=config.dev)
        else:
            _parser().print_help()
    except Exception as exc:
        print(f"chronicle: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
