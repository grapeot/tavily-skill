#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from dotenv import load_dotenv

USAGE_URL = "https://api.tavily.com/usage"

DEFAULT_MAX_RESULTS = 6
DEFAULT_SEARCH_DEPTH = "advanced"
DEFAULT_TOPIC = "general"
DEFAULT_RAW_CONTENT = "markdown"
DEFAULT_TIMEOUT = 60
DEFAULT_CONCURRENCY = 4
DEFAULT_EXTRACT_DEPTH = "advanced"
DEFAULT_EXTRACT_FORMAT = "markdown"
SEARCH_DEPTH_CHOICES = ["basic", "advanced", "fast", "ultra-fast"]
TOPIC_CHOICES = ["general", "news", "finance"]
TIME_RANGE_CHOICES = ["day", "week", "month", "year"]
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


def _fetch_usage(api_key: str, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    request = urllib.request.Request(
        USAGE_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Tavily usage request failed with HTTP {exc.code}: {detail or exc.reason}")
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
        raise RuntimeError(f"Tavily usage request failed: {exc}")

    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError("Tavily usage response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Tavily usage response was not a JSON object")
    return payload


def _normalize_usage_response(response: dict[str, Any], timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    key = response.get("key") if isinstance(response.get("key"), dict) else {}
    account = response.get("account") if isinstance(response.get("account"), dict) else {}

    plan_usage = account.get("plan_usage")
    plan_limit = account.get("plan_limit")
    remaining = None
    if isinstance(plan_usage, (int, float)) and isinstance(plan_limit, (int, float)):
        remaining = plan_limit - plan_usage

    breakdown = {
        name: account.get(f"{name}_usage")
        for name in ("search", "crawl", "extract", "map", "research")
    }

    return {
        "command": "usage",
        "input": {"timeout": timeout},
        "data": {
            "plan": account.get("current_plan"),
            "plan_usage": plan_usage,
            "plan_limit": plan_limit,
            "remaining_credits": remaining,
            "breakdown": breakdown,
            "paygo_usage": account.get("paygo_usage"),
            "paygo_limit": account.get("paygo_limit"),
            "key_usage": key.get("usage"),
            "key_limit": key.get("limit"),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tavily search CLI")
    parser.add_argument("--env-file", help="Optional .env file path")

    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search the web with Tavily")
    search_parser.add_argument(
        "query",
        nargs="?",
        help="Search query (single mode; mutually exclusive with --query)",
    )
    search_parser.add_argument(
        "--query",
        dest="queries",
        action="append",
        default=None,
        help=(
            "Run a batch of independent searches in one process; repeat for each query. "
            "Each value is a complete query string. Mutually exclusive with the positional query."
        ),
    )
    search_parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Max parallel searches in batch mode (default: {DEFAULT_CONCURRENCY})",
    )
    search_parser.add_argument(
        "--serial",
        action="store_true",
        help="Force sequential batch execution; overrides --concurrency",
    )
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

    usage_parser = subparsers.add_parser("usage", help="Show Tavily account credit usage")
    usage_parser.set_defaults(stdout=False)
    usage_parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the full JSON payload to stdout instead of writing it to the default output file",
    )
    usage_parser.add_argument(
        "--output",
        help="Write the full usage payload to a file and return status JSON on stdout",
    )
    usage_parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )

    return parser


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.command == "usage":
        if args.timeout <= 0:
            parser.error("--timeout must be greater than 0.")
        if args.stdout and args.output:
            parser.error("Use either --stdout or --output, not both.")
        return
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
    has_positional = args.query is not None
    has_option = bool(args.queries)
    if has_positional and has_option:
        parser.error("Provide either a positional query or --query options, not both.")
    if not has_positional and not has_option:
        parser.error("Provide a positional query or at least one --query option.")
    if has_positional and not args.query.strip():
        parser.error("Search query must not be empty.")
    if has_option and any(not query.strip() for query in args.queries):
        parser.error("--query values must not be empty.")
    if has_option:
        # Batch mode: each query owns its auto-named file, so --stdout/--output are ambiguous.
        if args.stdout:
            parser.error("--stdout is not supported in batch mode (--query).")
        if args.output:
            parser.error("--output is not supported in batch mode (--query).")
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1.")
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


def _build_search_request(args: argparse.Namespace, query: str | None = None) -> dict[str, Any]:
    request: dict[str, Any] = {
        "query": args.query if query is None else query,
        "search_depth": args.search_depth,
        "topic": args.topic,
        "max_results": args.max_results,
        "include_answer": False,
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


def _normalize_search_response(
    args: argparse.Namespace,
    response: dict[str, Any],
    query: str | None = None,
) -> dict[str, Any]:
    images = response.get("images") or []
    results = response.get("results") or []
    effective_query = args.query if query is None else query

    return {
        "command": "search",
        "input": {
            "query": effective_query,
            "max_results": args.max_results,
            "search_depth": args.search_depth,
            "topic": args.topic,
            "time_range": args.time_range,
            "start_date": args.start_date,
            "end_date": args.end_date,
            "include_domains": args.include_domains,
            "exclude_domains": args.exclude_domains,
            "include_images": args.include_images,
            "include_image_descriptions": args.include_image_descriptions,
            "raw_content": args.raw_content,
            "country": args.country,
            "timeout": args.timeout,
        },
        "data": {
            "query": response.get("query", effective_query),
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


def _default_output_path_for_search(query: str) -> str:
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify(query)
    return str(get_default_output_dir() / f"search_{timestamp}_{slug}.json")


def _default_output_path(args: argparse.Namespace) -> str:
    if args.command == "search":
        return _default_output_path_for_search(args.query)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.command == "extract":
        seed = args.urls[0]
    else:
        seed = args.command
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
    if command == "usage":
        return {
            **base,
            "data": {
                "plan": "string|null",
                "plan_usage": "number|null",
                "plan_limit": "number|null",
                "remaining_credits": "number|null",
                "breakdown": "object",
                "paygo_usage": "number|null",
                "paygo_limit": "number|null",
                "key_usage": "number|null",
                "key_limit": "number|null",
            },
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


def _effective_concurrency(args: argparse.Namespace) -> int:
    if getattr(args, "serial", False):
        return 1
    return args.concurrency


def _batch_output_paths(queries: list[str]) -> list[str]:
    """Reserve one unique auto-named output path per query.

    Paths are computed up front on the main thread so that concurrent workers
    never race on filename allocation. Colliding names get a numeric suffix.
    """
    used: set[str] = set()
    paths: list[str] = []
    for query in queries:
        base = _default_output_path_for_search(query)
        base_path = Path(base)
        candidate = base
        index = 1
        while candidate in used or Path(candidate).exists():
            candidate = str(base_path.with_name(f"{base_path.stem}_{index}{base_path.suffix}"))
            index += 1
        used.add(candidate)
        paths.append(candidate)
    return paths


def _write_payload_file(payload: dict[str, Any], output_path: str) -> int:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    target = Path(output_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def _run_batch_query(
    client: SearchClient,
    args: argparse.Namespace,
    query: str,
    output_path: str,
) -> dict[str, Any]:
    request = _build_search_request(args, query)
    response = client.search(**request)
    payload = _normalize_search_response(args, response, query)
    _write_payload_file(payload, output_path)
    return {
        "query": query,
        "output_path": output_path,
        "summary": {
            "result_count": payload["data"].get("result_count"),
            "image_count": payload["data"].get("image_count"),
        },
        "error": None,
    }


def _batch_error(exc: Exception) -> dict[str, Any]:
    http_status = getattr(exc, "status_code", None)
    if not isinstance(http_status, int):
        http_status = None
    return {"http_status": http_status, "error": str(exc)}


def _batch_payload_schema() -> dict[str, Any]:
    return {
        "command": "search",
        "status": "ok|partial|error",
        "output_mode": "batch",
        "output_dir": "string",
        "input": {
            "queries": "array",
            "concurrency": "number",
            "serial": "boolean",
            "max_results": "number",
            "search_depth": "string",
            "topic": "string",
            "time_range": "string|null",
            "start_date": "string|null",
            "end_date": "string|null",
            "include_domains": "array",
            "exclude_domains": "array",
            "include_images": "boolean",
            "raw_content": "string",
            "country": "string|null",
            "timeout": "number",
        },
        "summary": {
            "query_count": "number",
            "success_count": "number",
            "failed_count": "number",
            "credits_used": "null",
        },
        "results": [{
            "query": "string",
            "output_path": "string|null",
            "summary": "object|null",
            "error": "object|null",
        }],
    }


def run_search_batch(client: SearchClient, args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    """Run every --query in one process and return (status envelope, exit code).

    A single Tavily SDK client is shared across worker threads. This is safe only
    while the SDK stays effectively stateless over HTTP; if a future version keeps
    non-thread-safe state, build one client per call instead. Output files are
    written per query, preserving the "one query = one file" corpus invariant.
    """
    queries = list(args.queries)
    paths = _batch_output_paths(queries)
    concurrency = _effective_concurrency(args)
    entries: list[dict[str, Any] | None] = [None] * len(queries)

    def worker(index: int) -> None:
        try:
            entries[index] = _run_batch_query(client, args, queries[index], paths[index])
        except Exception as exc:  # noqa: BLE001 - per-query isolation is the point
            entries[index] = {
                "query": queries[index],
                "output_path": None,
                "summary": None,
                "error": _batch_error(exc),
            }

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)
    try:
        list(executor.map(worker, range(len(queries))))
    except KeyboardInterrupt:
        # Do not wait for running workers on Ctrl-C; let main() return 130 promptly.
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)

    resolved = [entry for entry in entries if entry is not None]
    failed_count = sum(1 for entry in resolved if entry["error"])
    success_count = len(queries) - failed_count
    if failed_count == 0:
        status = "ok"
    elif success_count == 0:
        status = "error"
    else:
        status = "partial"

    envelope = {
        "command": "search",
        "status": status,
        "output_mode": "batch",
        "output_dir": str(get_default_output_dir()),
        "input": {
            "queries": queries,
            "concurrency": concurrency,
            "serial": bool(getattr(args, "serial", False)),
            "max_results": args.max_results,
            "search_depth": args.search_depth,
            "topic": args.topic,
            "time_range": args.time_range,
            "start_date": args.start_date,
            "end_date": args.end_date,
            "include_domains": args.include_domains,
            "exclude_domains": args.exclude_domains,
            "include_images": args.include_images,
            "raw_content": args.raw_content,
            "country": args.country,
            "timeout": args.timeout,
        },
        "summary": {
            "query_count": len(queries),
            "success_count": success_count,
            "failed_count": failed_count,
            "credits_used": None,
        },
        "results": resolved,
        "payload_schema": _batch_payload_schema(),
    }
    return envelope, (1 if success_count == 0 else 0)


def emit_search_batch(envelope: dict[str, Any]) -> int:
    print(json.dumps(envelope, ensure_ascii=False, indent=2))
    summary = envelope["summary"]
    if summary["failed_count"]:
        print(
            f"Warning: {summary['failed_count']}/{summary['query_count']} "
            "queries failed in batch mode",
            file=sys.stderr,
        )
    if summary["success_count"] == 0:
        return 1
    return 0


def run_extract(client: SearchClient, args: argparse.Namespace) -> dict[str, Any]:
    request = _build_extract_request(args)
    response = client.extract(**request)
    return _normalize_extract_response(args, response)


def run_usage(args: argparse.Namespace, api_key: str) -> dict[str, Any]:
    response = _fetch_usage(api_key, args.timeout)
    return _normalize_usage_response(response, args.timeout)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_args(parser, args)
    load_workspace_env(args.env_file)

    try:
        if args.command == "usage":
            payload = run_usage(args, _get_api_key())
            _emit_payload(payload, _resolve_output_path(args))
            return 0
        client = _build_client()
        if args.command == "search":
            if args.queries:
                envelope, _ = run_search_batch(client, args)
                return emit_search_batch(envelope)
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
