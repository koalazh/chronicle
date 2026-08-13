from __future__ import annotations

import argparse
import json
import sys

import uvicorn

from .app import create_app
from .config import is_loopback_host, load_config
from .crisis import validate_volume
from .doctor import doctor


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chronicle", description="Chronicle: 甲申 command line")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("version")
    volume = sub.add_parser("volume")
    volume.add_subparsers(dest="volume_command").add_parser("validate")
    sub.add_parser("doctor")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    start = sub.add_parser("start")
    start.add_argument("--host", default=None)
    start.add_argument("--port", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = load_config()
    try:
        if args.command == "version":
            print("Chronicle: 甲申 0.1.0")
        elif args.command == "volume" and args.volume_command == "validate":
            print("\n".join(validate_volume(config.volume_path)))
        elif args.command == "doctor":
            result = doctor(config)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] == "READY" else 1
        elif args.command in {"serve", "start"}:
            requested_host = args.host or config.host
            if not is_loopback_host(requested_host):
                raise ValueError("Chronicle only supports loopback host binding")
            product_start = args.command == "start"
            if config.dev and not product_start:
                app = "chronicle.app:app"
            else:
                app = create_app(config)
            uvicorn.run(
                app,
                host=requested_host,
                port=args.port or config.port,
                reload=config.dev and not product_start,
            )
        else:
            _parser().print_help()
    except Exception as exc:
        print(f"chronicle: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
