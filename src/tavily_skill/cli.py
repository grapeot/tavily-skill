#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Protocol

from dotenv import load_dotenv

DEFAULT_MAX_RESULTS = 6
DEFAULT_SEARCH_DEPTH = "advanced"
DEFAULT_TOPIC = "general"
DEFAULT_ANSWER_MODE = "off"
DEFAULT_RAW_CONTENT = "markdown"
DEFAULT_TIMEOUT = 60
DEFAULT_EXTRACT_DEPTH = "advanced"
DEFAULT_EXTRACT_FORMAT = "markdown"
SEARCH_DEPTH_CHOICES = ["basic", "advanced", "fast", "ultra-fast"]
TOPIC_CHOICES = ["general", "news", "finance"]
TIME_RANGE_CHOICES = ["day", "week", "month", "year"]
ANSWER_CHOICES = ["off", "basic", "advanced"]
RAW_CONTENT_CHOICES = ["off", "markdown", "text"]
EXTRACT_DEPTH_CHOICES = ["basic", "advanced"]
EXTRACT_FORMAT_CHOICES = ["markdown", "text"]

# Optional 1Password reference, e.g. op://Vault/Item/field — never commit real vault paths.
_ONEPASSWORD_REF_ENV = "ONEPASSWORD_TAVILY_REFERENCE"
_OUTPUT_DIR_ENV = "TAVILY_CLI_OUTPUT_DIR"


class SearchClient(Protocol):
    def search(self, **kwargs: object) -> dict[str, object]: ...

    def extract(self, **kwargs: object) -> dict[str, object]: ...


def get_default_output_dir() -> Path:
    raw = os.environ.get(_OUTPUT_DIR_ENV)
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.cwd() / "tmp" / "tavily"


def _load_env_file(env_file: Path) -> bool:
    if not env_file.exists():
        return False
    load_dotenv(env_file, override=False)
    return True


def load_workspace_env(explicit_env_file: str | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit_env_file:
        candidates.append(Path(explicit_env_file).expanduser().resolve())

    cwd = Path.cwd()
    candidates.extend((parent / ".env") for parent in [cwd] + list(cwd.parents))

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if _load_env_file(candidate):
            return candidate
    return None


def _onepassword_reference() -> str | None:
    return os.environ.get(_ONEPASSWORD_REF_ENV)


def _get_api_key_from_1password() -> str | None:
    reference = _onepassword_reference()
    if not reference:
        return None
    try:
        result = subprocess.run(
            ["op", "read", reference],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _get_api_key() -> str:
    api_key = os.environ.get("TAVILY_API_KEY")
    if api_key:
        return api_key

    api_key = _get_api_key_from_1password()
    if api_key:
        return api_key

    raise RuntimeError(
        "Tavily API key not found. Set TAVILY_API_KEY, or set "
        f"{_ONEPASSWORD_REF_ENV} to an `op read`-compatible secret reference "
        "and ensure the 1Password CLI is logged in."
    )


def _build_client() -> SearchClient:
    tavily_module = __import__("tavily")
    client_class = getattr(tavily_module, "TavilyClient")
    return client_class(api_key=_get_api_key())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tavily search CLI")
    parser.add_argument("--env-file", help="Optional .env file path")

    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search the web with Tavily")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument(
        "--max-results",
        type=int,
        default=DEFAULT_MAX_RESULTS,
        help=f"Maximum number of results (default: {DEFAULT_MAX_RESULTS})",
    )
    search_parser.add_argument(
        "--search-depth",
        choices=SEARCH_DEPTH_CHOICES,
        default=DEFAULT_SEARCH_DEPTH,
        help=f"Search depth (default: {DEFAULT_SEARCH_DEPTH})",
    )
    search_parser.add_argument(
        "--topic",
        choices=TOPIC_CHOICES,
        default=DEFAULT_TOPIC,
        help=f"Search topic (default: {DEFAULT_TOPIC})",
    )
    search_parser.add_argument(
        "--time-range",
        choices=TIME_RANGE_CHOICES,
        help="Only include results from a recent time range",
    )
    search_parser.add_argument("--start-date", help="Return results on or after YYYY-MM-DD")
    search_parser.add_argument("--end-date", help="Return results on or before YYYY-MM-DD")
    search_parser.add_argument(
        "--include-domain",
        dest="include_domains",
        action="append",
        default=[],
        help="Restrict results to a domain; repeat for multiple domains",
    )
    search_parser.add_argument(
        "--exclude-domain",
        dest="exclude_domains",
        action="append",
        default=[],
        help="Exclude a domain; repeat for multiple domains",
    )
    search_parser.add_argument(
        "--answer",
        choices=ANSWER_CHOICES,
        default=DEFAULT_ANSWER_MODE,
        help=f"Answer mode (default: {DEFAULT_ANSWER_MODE})",
    )
    search_parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the full JSON payload to stdout instead of writing it to the default output file",
    )
    search_parser.add_argument(
        "--raw-content",
        choices=RAW_CONTENT_CHOICES,
        default=DEFAULT_RAW_CONTENT,
        help=f"Include raw page content in each result (default: {DEFAULT_RAW_CONTENT})",
    )
    search_parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    search_parser.add_argument(
        "--country",
        help="Optional country boost, for example 'United States'",
    )
    search_parser.add_argument(
        "--output",
        help="Also write the JSON payload to a file path",
    )
    search_parser.set_defaults(include_images=False, include_image_descriptions=False)
    search_parser.add_argument(
        "--images",
        dest="include_images",
        action="store_true",
        help="Enable image results",
    )
    search_parser.add_argument(
        "--no-images",
        dest="include_images",
        action="store_false",
        help="Disable image results",
    )
    search_parser.add_argument(
        "--image-descriptions",
        dest="include_image_descriptions",
        action="store_true",
        help="When image results are enabled, also include LLM-generated image descriptions",
    )
    search_parser.add_argument(
        "--no-image-descriptions",
        dest="include_image_descriptions",
        action="store_false",
        help="Return image URLs without descriptions",
    )

    extract_parser = subparsers.add_parser("extract", help="Extract content from URLs with Tavily")
    extract_parser.add_argument("urls", nargs="+", help="One or more URLs to extract")
    extract_parser.add_argument(
        "--extract-depth",
        choices=EXTRACT_DEPTH_CHOICES,
        default=DEFAULT_EXTRACT_DEPTH,
        help=f"Extraction depth (default: {DEFAULT_EXTRACT_DEPTH})",
    )
    extract_parser.add_argument(
        "--format",
        choices=EXTRACT_FORMAT_CHOICES,
        default=DEFAULT_EXTRACT_FORMAT,
        help=f"Extracted content format (default: {DEFAULT_EXTRACT_FORMAT})",
    )
    extract_parser.add_argument(
        "--query",
        help="Optional query to keep only the most relevant chunks",
    )
    extract_parser.add_argument(
        "--chunks-per-source",
        type=int,
        help="Relevant chunks per URL when query is provided",
    )
    extract_parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    extract_parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the full JSON payload to stdout instead of writing it to the default output file",
    )
    extract_parser.add_argument(
        "--output",
        help="Write the full extract payload to a file and return status JSON on stdout",
    )
    extract_parser.set_defaults(include_images=False, include_favicon=False)
    extract_parser.add_argument(
        "--images",
        dest="include_images",
        action="store_true",
        help="Enable image extraction",
    )
    extract_parser.add_argument(
        "--no-images",
        dest="include_images",
        action="store_false",
        help="Disable image extraction",
    )
    extract_parser.add_argument(
        "--favicon",
        dest="include_favicon",
        action="store_true",
        help="Include favicon URLs in extract results",
    )

    return parser


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.command != "search":
        if args.command == "extract":
            if args.timeout <= 0:
                parser.error("--timeout must be greater than 0.")
            if args.stdout and args.output:
                parser.error("Use either --stdout or --output, not both.")
            if not 1 <= len(args.urls) <= 20:
                parser.error("extract accepts between 1 and 20 URLs.")
            if args.chunks_per_source is not None and args.chunks_per_source <= 0:
                parser.error("--chunks-per-source must be greater than 0.")
            if args.chunks_per_source is not None and not args.query:
                parser.error("--chunks-per-source requires --query.")
        return
    if args.time_range and (args.start_date or args.end_date):
        parser.error("Use either --time-range or --start-date/--end-date, not both.")
    if args.stdout and args.output:
        parser.error("Use either --stdout or --output, not both.")
    if not 1 <= args.max_results <= 20:
        parser.error("--max-results must be between 1 and 20.")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than 0.")
    if getattr(args, "include_image_descriptions", False) and not args.include_images:
        args.include_images = True


def _build_search_request(args: argparse.Namespace) -> dict[str, Any]:
    include_answer: str | bool = False
    if args.answer != "off":
        include_answer = args.answer

    request: dict[str, Any] = {
        "query": args.query,
        "search_depth": args.search_depth,
        "topic": args.topic,
        "max_results": args.max_results,
        "include_answer": include_answer,
        "include_images": args.include_images,
        "include_image_descriptions": args.include_image_descriptions,
        "include_usage": True,
        "timeout": args.timeout,
    }
    if args.raw_content != "off":
        request["include_raw_content"] = args.raw_content
    if args.time_range:
        request["time_range"] = args.time_range
    if args.start_date:
        request["start_date"] = args.start_date
    if args.end_date:
        request["end_date"] = args.end_date
    if args.start_date or args.end_date:
        request["days"] = None
    if args.include_domains:
        request["include_domains"] = args.include_domains
    if args.exclude_domains:
        request["exclude_domains"] = args.exclude_domains
    if args.country:
        request["country"] = args.country
    return request


def _normalize_search_response(args: argparse.Namespace, response: dict[str, Any]) -> dict[str, Any]:
    images = response.get("images") or []
    results = response.get("results") or []

    return {
        "command": "search",
        "input": {
            "query": args.query,
            "max_results": args.max_results,
            "search_depth": args.search_depth,
            "topic": args.topic,
            "time_range": args.time_range,
            "start_date": args.start_date,
            "end_date": args.end_date,
            "include_domains": args.include_domains,
            "exclude_domains": args.exclude_domains,
            "answer": args.answer,
            "include_images": args.include_images,
            "include_image_descriptions": args.include_image_descriptions,
            "raw_content": args.raw_content,
            "country": args.country,
            "timeout": args.timeout,
        },
        "data": {
            "query": response.get("query", args.query),
            "answer": response.get("answer"),
            "results": results,
            "images": images,
            "response_time": response.get("response_time"),
            "request_id": response.get("request_id"),
            "usage": response.get("usage"),
            "result_count": len(results),
            "image_count": len(images),
        },
    }


def _build_extract_request(args: argparse.Namespace) -> dict[str, Any]:
    request: dict[str, Any] = {
        "urls": args.urls,
        "extract_depth": args.extract_depth,
        "format": args.format,
        "include_images": args.include_images,
        "include_usage": True,
        "timeout": args.timeout,
    }
    if args.query:
        request["query"] = args.query
    if args.chunks_per_source is not None:
        request["chunks_per_source"] = args.chunks_per_source
    if args.include_favicon:
        request["include_favicon"] = True
    return request


def _normalize_extract_response(args: argparse.Namespace, response: dict[str, Any]) -> dict[str, Any]:
    results = response.get("results") or []
    failed_results = response.get("failed_results") or []
    image_count = 0
    for result in results:
        if isinstance(result, dict):
            images = result.get("images") or []
            if isinstance(images, list):
                image_count += len(images)

    return {
        "command": "extract",
        "input": {
            "urls": args.urls,
            "extract_depth": args.extract_depth,
            "format": args.format,
            "query": args.query,
            "chunks_per_source": args.chunks_per_source,
            "include_images": args.include_images,
            "include_favicon": args.include_favicon,
            "timeout": args.timeout,
        },
        "data": {
            "results": results,
            "failed_results": failed_results,
            "usage": response.get("usage"),
            "result_count": len(results),
            "failed_count": len(failed_results),
            "image_count": image_count,
        },
    }


def _emit_payload(payload: dict[str, Any], output_path: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not output_path:
        print(text)
        return

    target = Path(output_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")

    command = payload.get("command")
    status_payload = {
        "command": command,
        "status": "ok",
        "output_mode": "file",
        "output_path": str(target),
        "payload_bytes": len(text.encode("utf-8")),
        "summary": {
            "result_count": payload.get("data", {}).get("result_count"),
            "failed_count": payload.get("data", {}).get("failed_count"),
            "image_count": payload.get("data", {}).get("image_count"),
            "has_answer": bool(payload.get("data", {}).get("answer")),
        },
        "payload_schema": _payload_schema(command),
    }
    print(json.dumps(status_payload, ensure_ascii=False, indent=2))
    print(f"Saved JSON to {target}", file=sys.stderr)


def _slugify(value: str, max_length: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    if not slug:
        return "payload"
    return slug[:max_length].rstrip("_") or "payload"


def _default_output_path(args: argparse.Namespace) -> str:
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.command == "search":
        seed = args.query
    else:
        seed = args.urls[0]
    slug = _slugify(seed)
    return str(get_default_output_dir() / f"{args.command}_{timestamp}_{slug}.json")


def _resolve_output_path(args: argparse.Namespace) -> str | None:
    if getattr(args, "stdout", False):
        return None
    if getattr(args, "output", None):
        return args.output
    return _default_output_path(args)


def _payload_schema(command: object) -> dict[str, Any]:
    base = {
        "command": "string",
        "input": "object",
    }
    if command == "extract":
        return {
            **base,
            "data": {
                "results": "array",
                "failed_results": "array",
                "usage": "object|null",
                "result_count": "number",
                "failed_count": "number",
                "image_count": "number",
            },
        }
    return {
        **base,
        "data": {
            "query": "string",
            "answer": "string|null",
            "results": "array",
            "images": "array",
            "response_time": "number|null",
            "request_id": "string|null",
            "usage": "object|null",
            "result_count": "number",
            "image_count": "number",
        },
    }


def run_search(client: SearchClient, args: argparse.Namespace) -> dict[str, Any]:
    request = _build_search_request(args)
    response = client.search(**request)
    return _normalize_search_response(args, response)


def run_extract(client: SearchClient, args: argparse.Namespace) -> dict[str, Any]:
    request = _build_extract_request(args)
    response = client.extract(**request)
    return _normalize_extract_response(args, response)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_args(parser, args)
    load_workspace_env(args.env_file)

    try:
        client = _build_client()
        if args.command == "search":
            payload = run_search(client, args)
        elif args.command == "extract":
            payload = run_extract(client, args)
        else:
            parser.error(f"Unsupported command: {args.command}")
            return 1
        _emit_payload(payload, _resolve_output_path(args))
        return 0
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
