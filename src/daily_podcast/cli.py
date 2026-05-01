from __future__ import annotations

import argparse
import logging
from pathlib import Path

from openai import APIConnectionError, AuthenticationError, OpenAIError, RateLimitError
from pydantic import ValidationError

from .config import load_app_config
from .runner import DailyPodcastAgent
from .scheduler import run_daemon

DEFAULT_CONFIG_PATH = Path("config/subjects.yaml")


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, AuthenticationError):
        return (
            "OpenAI rejected the configured API key. Update OPENAI_API_KEY in .env "
            "with a valid key from https://platform.openai.com/api-keys."
        )
    if isinstance(exc, RateLimitError):
        message = str(exc)
        if "insufficient_quota" in message:
            return (
                "OpenAI returned insufficient_quota for the configured API key. "
                "Add billing/credits or use a different OPENAI_API_KEY, then run again."
            )
        return "OpenAI rate-limited this request. Wait a bit, then run again."
    if isinstance(exc, APIConnectionError):
        return "Could not connect to OpenAI. Check your internet connection and try again."
    if isinstance(exc, OpenAIError):
        return f"OpenAI request failed: {exc}"
    if isinstance(exc, ValidationError):
        return f"Configuration is invalid:\n{exc}"
    if isinstance(exc, FileNotFoundError):
        return f"Required file not found: {exc.filename}"
    return str(exc)


def main() -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--log-level", default="INFO", help="Python logging level.")

    parser = argparse.ArgumentParser(prog="daily-podcast", parents=[common])
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run", parents=[common], help="Generate today's news digest from config/subjects.yaml.")
    send_existing = subparsers.add_parser(
        "send-existing",
        parents=[common],
        help="Send an already generated digest without calling OpenAI or TTS.",
    )
    send_existing.add_argument(
        "--run-dir",
        type=Path,
        help="Existing artifact directory. Defaults to output/YYYY-MM-DD for today.",
    )
    subparsers.add_parser("daemon", parents=[common], help="Run scheduler and send at configured time.")
    subparsers.add_parser("show-config", parents=[common], help="Validate and print the loaded configuration.")

    args = parser.parse_args()
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(message)s")

    try:
        config = load_app_config(DEFAULT_CONFIG_PATH)

        if args.command == "run":
            result = DailyPodcastAgent(config).run_once()
            print(f"Gmail message: {result['message_id']}")
            print(f"Audio: {result['audio_path']}")
            print(f"Summary: {result['summary_path']}")
            print(f"HTML Summary: {result['html_summary_path']}")
            print(f"Script: {result['script_path']}")
            print(f"Artifacts: {result['run_dir']}")
        elif args.command == "send-existing":
            result = DailyPodcastAgent(config).send_existing(args.run_dir)
            print(f"Sent Gmail message {result['message_id']}")
            print(f"Audio: {result['audio_path']}")
            print(f"Artifacts: {result['run_dir']}")
        elif args.command == "daemon":
            run_daemon(config)
        elif args.command == "show-config":
            print(config.subjects_file.model_dump_json(indent=2))
    except Exception as exc:
        logging.error(_friendly_error(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
