from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

import tavily_skill.cli as tavily_cli  # noqa: E402


class StubClient:
    def __init__(self) -> None:
        self.search_calls: list[dict[str, object]] = []
        self.extract_calls: list[dict[str, object]] = []

    def search(self, **kwargs: object) -> dict[str, object]:
        self.search_calls.append(kwargs)
        return {
            "query": kwargs["query"],
            "results": [{"url": "https://example.com", "title": "Example", "content": "demo"}],
            "images": [{"url": "https://example.com/image.png", "description": "demo"}],
            "response_time": 1.2,
            "request_id": "req_123",
            "usage": {"credits": 1},
        }

    def extract(self, **kwargs: object) -> dict[str, object]:
        self.extract_calls.append(kwargs)
        return {
            "results": [{
                "url": kwargs["urls"][0],
                "raw_content": "content",
                "images": ["https://example.com/image.png"],
            }],
            "failed_results": [],
            "usage": {"credits": 1},
        }


def _build_parser() -> argparse.ArgumentParser:
    return tavily_cli.build_parser()


def test_search_parser_defaults() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "latest ai"])

    assert args.command == "search"
    assert args.max_results == 6
    assert args.search_depth == "advanced"
    assert args.include_images is False
    assert args.include_image_descriptions is False
    assert args.raw_content == "markdown"
    assert args.stdout is False


def test_search_parser_rejects_answer_option() -> None:
    parser = _build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["search", "latest ai", "--answer", "basic"])


def test_extract_parser_defaults() -> None:
    parser = _build_parser()
    args = parser.parse_args(["extract", "https://example.com"])

    assert args.command == "extract"
    assert args.extract_depth == "advanced"
    assert args.format == "markdown"
    assert args.include_images is False
    assert args.include_favicon is False
    assert args.stdout is False


def test_validate_search_conflicting_dates() -> None:
    parser = _build_parser()
    args = parser.parse_args([
        "search",
        "latest ai",
        "--time-range",
        "week",
        "--start-date",
        "2026-03-01",
    ])

    with pytest.raises(SystemExit):
        tavily_cli._validate_args(parser, args)


def test_validate_extract_requires_query_for_chunks() -> None:
    parser = _build_parser()
    args = parser.parse_args([
        "extract",
        "https://example.com",
        "--chunks-per-source",
        "2",
    ])

    with pytest.raises(SystemExit):
        tavily_cli._validate_args(parser, args)


def test_build_search_request() -> None:
    parser = _build_parser()
    args = parser.parse_args([
        "search",
        "latest ai",
        "--max-results",
        "10",
        "--include-domain",
        "github.com",
        "--exclude-domain",
        "medium.com",
        "--time-range",
        "month",
    ])

    request = tavily_cli._build_search_request(args)

    assert request["query"] == "latest ai"
    assert request["max_results"] == 10
    assert request["include_domains"] == ["github.com"]
    assert request["exclude_domains"] == ["medium.com"]
    assert request["time_range"] == "month"
    assert request["include_answer"] is False
    assert request["include_raw_content"] == "markdown"


def test_search_raw_content_can_be_disabled() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "latest ai", "--raw-content", "off"])

    request = tavily_cli._build_search_request(args)

    assert "include_raw_content" not in request


def test_search_no_images_disables_image_descriptions() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "latest ai", "--no-images"])

    tavily_cli._validate_args(parser, args)

    assert args.include_images is False
    assert args.include_image_descriptions is False


def test_search_images_can_be_enabled_explicitly() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "latest ai", "--images", "--image-descriptions"])

    tavily_cli._validate_args(parser, args)

    assert args.include_images is True
    assert args.include_image_descriptions is True


def test_search_image_descriptions_imply_images() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "latest ai", "--image-descriptions"])

    tavily_cli._validate_args(parser, args)

    assert args.include_images is True
    assert args.include_image_descriptions is True


def test_extract_images_can_be_enabled_explicitly() -> None:
    parser = _build_parser()
    args = parser.parse_args(["extract", "https://example.com", "--images"])

    tavily_cli._validate_args(parser, args)

    assert args.include_images is True


def test_validate_search_rejects_stdout_with_output() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "latest ai", "--stdout", "--output", "/tmp/out.json"])

    with pytest.raises(SystemExit):
        tavily_cli._validate_args(parser, args)


def test_validate_extract_rejects_stdout_with_output() -> None:
    parser = _build_parser()
    args = parser.parse_args([
        "extract",
        "https://example.com",
        "--stdout",
        "--output",
        "/tmp/out.json",
    ])

    with pytest.raises(SystemExit):
        tavily_cli._validate_args(parser, args)


def test_build_extract_request() -> None:
    parser = _build_parser()
    args = parser.parse_args([
        "extract",
        "https://example.com",
        "https://example.org",
        "--query",
        "agent",
        "--chunks-per-source",
        "3",
        "--favicon",
    ])

    request = tavily_cli._build_extract_request(args)

    assert request["urls"] == ["https://example.com", "https://example.org"]
    assert request["query"] == "agent"
    assert request["chunks_per_source"] == 3
    assert request["include_favicon"] is True


def test_normalize_search_response() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "latest ai"])
    response = {
        "query": "latest ai",
        "results": [{"url": "https://example.com"}],
        "images": [{"url": "https://example.com/image.png"}],
        "response_time": 0.8,
        "request_id": "req_123",
        "usage": {"credits": 1},
    }

    payload = tavily_cli._normalize_search_response(args, response)

    assert payload["command"] == "search"
    assert payload["data"]["result_count"] == 1
    assert payload["data"]["image_count"] == 1


def test_normalize_search_response_drops_answer() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "latest ai"])

    payload = tavily_cli._normalize_search_response(args, {"answer": "must not leak"})

    assert "answer" not in payload["input"]
    assert "answer" not in payload["data"]


def test_normalize_extract_response() -> None:
    parser = _build_parser()
    args = parser.parse_args(["extract", "https://example.com"])
    response = {
        "results": [{"url": "https://example.com", "raw_content": "text", "images": ["a", "b"]}],
        "failed_results": [{"url": "https://bad.example", "error": "failed"}],
        "usage": {"credits": 2},
    }

    payload = tavily_cli._normalize_extract_response(args, response)

    assert payload["command"] == "extract"
    assert payload["data"]["result_count"] == 1
    assert payload["data"]["failed_count"] == 1
    assert payload["data"]["image_count"] == 2


def test_emit_payload_stdout_only(capsys: pytest.CaptureFixture[str]) -> None:
    payload = {
        "command": "search",
        "input": {"query": "latest ai"},
        "data": {"result_count": 1, "image_count": 0},
    }

    tavily_cli._emit_payload(payload, None)

    captured = capsys.readouterr()
    assert json.loads(captured.out)["command"] == "search"
    assert captured.err == ""


def test_emit_payload_file_mode(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output_path = tmp_path / "search.json"
    payload = {
        "command": "search",
        "input": {"query": "latest ai"},
        "data": {"result_count": 2, "image_count": 1},
    }

    tavily_cli._emit_payload(payload, str(output_path))

    captured = capsys.readouterr()
    status_payload = json.loads(captured.out)
    assert status_payload["output_mode"] == "file"
    assert status_payload["output_path"] == str(output_path)
    assert status_payload["summary"]["result_count"] == 2
    assert "has_answer" not in status_payload["summary"]
    assert "answer" not in status_payload["payload_schema"]["data"]
    assert output_path.exists()
    assert "Saved JSON to" in captured.err


def test_emit_payload_file_mode_extract_schema(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output_path = tmp_path / "extract.json"
    payload = {
        "command": "extract",
        "input": {"urls": ["https://example.com"]},
        "data": {"result_count": 1, "failed_count": 0, "image_count": 1},
    }

    tavily_cli._emit_payload(payload, str(output_path))

    captured = capsys.readouterr()
    status_payload = json.loads(captured.out)
    assert "failed_results" in status_payload["payload_schema"]["data"]
    assert "query" not in status_payload["payload_schema"]["data"]


def test_default_output_path_search_uses_tmp_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    parser = _build_parser()
    args = parser.parse_args(["search", "Latest AI news"])

    output_path = tavily_cli._resolve_output_path(args)

    assert output_path is not None
    assert output_path.startswith(str(tavily_cli.get_default_output_dir()))
    assert output_path.endswith("latest_ai_news.json")


def test_default_output_path_extract_uses_first_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    parser = _build_parser()
    args = parser.parse_args(["extract", "https://example.com/path?q=1"])

    output_path = tavily_cli._resolve_output_path(args)

    assert output_path is not None
    assert output_path.startswith(str(tavily_cli.get_default_output_dir()))
    assert output_path.endswith("https_example_com_path_q_1.json")


def test_resolve_output_path_respects_stdout() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "latest ai", "--stdout"])

    assert tavily_cli._resolve_output_path(args) is None


def test_run_search_uses_client() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "latest ai"])
    client = StubClient()

    payload = tavily_cli.run_search(client, args)

    assert client.search_calls[0]["query"] == "latest ai"
    assert payload["data"]["result_count"] == 1


def test_run_extract_uses_client() -> None:
    parser = _build_parser()
    args = parser.parse_args(["extract", "https://example.com"])
    client = StubClient()

    payload = tavily_cli.run_extract(client, args)

    assert client.extract_calls[0]["urls"] == ["https://example.com"]
    assert payload["data"]["result_count"] == 1


# ---------------------------------------------------------------------------
# usage subcommand
# ---------------------------------------------------------------------------


def test_usage_parser_defaults() -> None:
    parser = _build_parser()
    args = parser.parse_args(["usage"])

    assert args.command == "usage"
    assert args.stdout is False
    assert args.output is None
    assert args.timeout == 60


def test_usage_validate_rejects_stdout_with_output() -> None:
    parser = _build_parser()
    args = parser.parse_args(["usage", "--stdout", "--output", "/tmp/out.json"])

    with pytest.raises(SystemExit):
        tavily_cli._validate_args(parser, args)


def test_usage_validate_rejects_nonpositive_timeout() -> None:
    parser = _build_parser()
    args = parser.parse_args(["usage", "--timeout", "0"])

    with pytest.raises(SystemExit):
        tavily_cli._validate_args(parser, args)


def test_normalize_usage_response() -> None:
    response = {
        "key": {"usage": 819, "limit": None, "search_usage": 715, "extract_usage": 104},
        "account": {
            "current_plan": "Bootstrap",
            "plan_usage": 1237,
            "plan_limit": 15000,
            "search_usage": 1129,
            "crawl_usage": 0,
            "extract_usage": 108,
            "map_usage": 0,
            "research_usage": 0,
            "paygo_usage": 0,
            "paygo_limit": None,
        },
    }

    payload = tavily_cli._normalize_usage_response(response, 60)

    assert payload["command"] == "usage"
    data = payload["data"]
    assert data["plan"] == "Bootstrap"
    assert data["plan_usage"] == 1237
    assert data["plan_limit"] == 15000
    assert data["remaining_credits"] == 13763
    assert data["breakdown"] == {"search": 1129, "crawl": 0, "extract": 108, "map": 0, "research": 0}
    assert data["key_usage"] == 819
    assert data["key_limit"] is None


def test_normalize_usage_response_handles_missing_fields() -> None:
    payload = tavily_cli._normalize_usage_response({}, 30)

    data = payload["data"]
    assert data["plan"] is None
    assert data["plan_usage"] is None
    assert data["plan_limit"] is None
    assert data["remaining_credits"] is None
    assert data["breakdown"] == {"search": None, "crawl": None, "extract": None, "map": None, "research": None}
    assert payload["input"]["timeout"] == 30


def test_normalize_usage_response_partial_account_has_no_remaining() -> None:
    response = {"account": {"current_plan": "Bootstrap", "plan_usage": 10}}

    payload = tavily_cli._normalize_usage_response(response)

    assert payload["data"]["remaining_credits"] is None


def test_usage_schema_registered() -> None:
    schema = tavily_cli._payload_schema("usage")
    assert "remaining_credits" in schema["data"]
    assert "results" not in schema["data"]


def test_run_usage_uses_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    parser = _build_parser()
    args = parser.parse_args(["usage", "--timeout", "15"])
    captured: dict[str, object] = {}

    def fake_fetch(api_key: str, timeout: float) -> dict[str, object]:
        captured["api_key"] = api_key
        captured["timeout"] = timeout
        return {"account": {"current_plan": "Bootstrap", "plan_usage": 1, "plan_limit": 10}}

    monkeypatch.setattr(tavily_cli, "_fetch_usage", fake_fetch)

    payload = tavily_cli.run_usage(args, "tvly-test")

    assert captured == {"api_key": "tvly-test", "timeout": 15}
    assert payload["data"]["remaining_credits"] == 9
    assert payload["input"]["timeout"] == 15


def test_usage_default_output_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(tavily_cli._OUTPUT_DIR_ENV, str(tmp_path))
    parser = _build_parser()
    args = parser.parse_args(["usage"])

    output_path = tavily_cli._resolve_output_path(args)

    assert output_path is not None
    assert "usage_" in Path(output_path).name


def _integration_enabled() -> bool:
    return os.environ.get("RUN_TAVILY_INTEGRATION") == "1"


def _require_integration() -> None:
    if not _integration_enabled():
        pytest.skip("set RUN_TAVILY_INTEGRATION=1 to run paid Tavily integration tests")


def _secret_available_via_env() -> bool:
    return bool(os.environ.get("TAVILY_API_KEY", "").strip())


def _secret_available_via_op_reference() -> bool:
    ref = os.environ.get("ONEPASSWORD_TAVILY_REFERENCE")
    if not ref:
        return False
    result = subprocess.run(
        ["op", "read", ref],
        capture_output=True,
        text=True,
        timeout=20,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _integration_credentials_ready() -> bool:
    return _secret_available_via_env() or _secret_available_via_op_reference()


def _require_live_credentials() -> None:
    _require_integration()
    if not _integration_credentials_ready():
        pytest.skip(
            "need TAVILY_API_KEY or ONEPASSWORD_TAVILY_REFERENCE (plus working op CLI) "
            "for integration tests"
        )


@pytest.mark.integration
def test_integration_credentials_are_configured() -> None:
    _require_integration()
    assert _integration_credentials_ready() is True


def _cli_env_without_explicit_key() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("TAVILY_API_KEY", None)
    prefix = str(SRC_ROOT)
    if env.get("PYTHONPATH"):
        env["PYTHONPATH"] = prefix + os.pathsep + env["PYTHONPATH"]
    else:
        env["PYTHONPATH"] = prefix
    return env


def _write_fake_tavily_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "tavily.py"
    module_path.write_text(
        """
from pathlib import Path
import json
import os

class TavilyClient:
    def __init__(self, api_key):
        log_path = os.environ.get('TAVILY_TEST_LOG')
        if log_path:
            Path(log_path).write_text(json.dumps({'api_key': api_key}), encoding='utf-8')

    def search(self, **kwargs):
        return {
            'query': kwargs['query'],
            'results': [{'url': 'https://example.com', 'title': 'fake', 'content': 'fake'}],
            'images': [],
            'response_time': 0.1,
            'request_id': 'fake_req',
            'usage': {'credits': 0},
        }

    def extract(self, **kwargs):
        return {
            'results': [{'url': kwargs['urls'][0], 'raw_content': 'fake content', 'images': []}],
            'failed_results': [],
            'usage': {'credits': 0},
        }
""".strip(),
        encoding="utf-8",
    )
    return module_path


@pytest.mark.integration
def test_search_cli_integration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _require_live_credentials()
    monkeypatch.chdir(tmp_path)

    output_path = tmp_path / "search_payload.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tavily_skill",
            "search",
            "Tavily official website",
            "--max-results",
            "2",
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=_cli_env_without_explicit_key(),
    )

    assert result.returncode == 0, result.stderr
    status_payload = json.loads(result.stdout)
    assert status_payload["status"] == "ok"
    assert status_payload["output_mode"] == "file"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["command"] == "search"
    assert payload["data"]["result_count"] >= 1
    assert "results" not in status_payload
    assert "Tavily official website" not in result.stdout


@pytest.mark.integration
def test_search_cli_defaults_to_file_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _require_live_credentials()
    monkeypatch.chdir(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tavily_skill",
            "search",
            "Tavily official website",
            "--max-results",
            "2",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=_cli_env_without_explicit_key(),
    )

    assert result.returncode == 0, result.stderr
    status_payload = json.loads(result.stdout)
    assert status_payload["status"] == "ok"
    assert status_payload["output_mode"] == "file"
    output_path = Path(status_payload["output_path"])
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["command"] == "search"
    output_path.unlink()


@pytest.mark.integration
def test_extract_cli_integration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _require_live_credentials()
    monkeypatch.chdir(tmp_path)

    output_path = tmp_path / "extract_payload.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tavily_skill",
            "extract",
            "https://tavily.com",
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=_cli_env_without_explicit_key(),
    )

    assert result.returncode == 0, result.stderr
    status_payload = json.loads(result.stdout)
    assert status_payload["status"] == "ok"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["command"] == "extract"
    assert payload["data"]["result_count"] >= 1
    assert "raw_content" not in result.stdout


@pytest.mark.integration
def test_cli_resolves_api_key_through_onepassword_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_integration()
    ref = os.environ.get("ONEPASSWORD_TAVILY_REFERENCE")
    if not ref:
        pytest.skip("need ONEPASSWORD_TAVILY_REFERENCE for this assertion")

    secret_result = subprocess.run(
        ["op", "read", ref],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert secret_result.returncode == 0
    expected_key = secret_result.stdout.strip()
    assert expected_key

    monkeypatch.chdir(tmp_path)
    log_path = tmp_path / "client_log.json"
    _write_fake_tavily_module(tmp_path)
    env = _cli_env_without_explicit_key()
    env["PYTHONPATH"] = f"{tmp_path}{os.pathsep}{env['PYTHONPATH']}"
    env["TAVILY_TEST_LOG"] = str(log_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tavily_skill",
            "search",
            "op auth verification",
            "--max-results",
            "1",
            "--output",
            str(tmp_path / "op_check.json"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert log_path.exists()
    logged = json.loads(log_path.read_text(encoding="utf-8"))
    assert logged["api_key"] == expected_key


# ---------------------------------------------------------------------------
# batch search mode (--query)
# ---------------------------------------------------------------------------


class SlowStubClient(StubClient):
    def __init__(self, delay: float = 0.5, fail_queries: set[str] | None = None) -> None:
        super().__init__()
        self.delay = delay
        self.fail_queries = fail_queries or set()

    def search(self, **kwargs: object) -> dict[str, object]:
        time.sleep(self.delay)
        query = kwargs["query"]
        if query in self.fail_queries:
            raise RuntimeError(f"boom: {query}")
        return super().search(**kwargs)


def _parse_search(queries: list[str], *extra: str) -> argparse.Namespace:
    parser = _build_parser()
    argv = ["search"]
    for query in queries:
        argv += ["--query", query]
    argv += list(extra)
    return parser.parse_args(argv)


def test_search_positional_still_single_mode() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "latest ai"])

    assert args.query == "latest ai"
    assert args.queries is None
    tavily_cli._validate_args(parser, args)


def test_search_query_option_single_mode() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "--query", "latest ai"])

    assert args.query is None
    assert args.queries == ["latest ai"]
    tavily_cli._validate_args(parser, args)


def test_search_query_option_keeps_multiword_queries_intact() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "--query", "a b c", "--query", "d e"])

    assert args.queries == ["a b c", "d e"]


def test_search_rejects_positional_and_query_together() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "positional", "--query", "option"])

    with pytest.raises(SystemExit):
        tavily_cli._validate_args(parser, args)


def test_search_rejects_missing_query() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search"])

    with pytest.raises(SystemExit):
        tavily_cli._validate_args(parser, args)


def test_search_rejects_empty_positional_query() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "   "])

    with pytest.raises(SystemExit):
        tavily_cli._validate_args(parser, args)


def test_search_batch_rejects_empty_query() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "--query", "ok", "--query", "  "])

    with pytest.raises(SystemExit):
        tavily_cli._validate_args(parser, args)


def test_search_batch_rejects_output_flag() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "--query", "a", "--output", "/tmp/out.json"])

    with pytest.raises(SystemExit):
        tavily_cli._validate_args(parser, args)


def test_search_batch_rejects_stdout_flag() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "--query", "a", "--stdout"])

    with pytest.raises(SystemExit):
        tavily_cli._validate_args(parser, args)


def test_search_batch_rejects_nonpositive_concurrency() -> None:
    parser = _build_parser()
    args = parser.parse_args(["search", "--query", "a", "--concurrency", "0"])

    with pytest.raises(SystemExit):
        tavily_cli._validate_args(parser, args)


def test_search_serial_overrides_concurrency() -> None:
    parallel = _parse_search(["a"], "--concurrency", "8")
    serial = _parse_search(["a"], "--concurrency", "8", "--serial")

    assert tavily_cli._effective_concurrency(parallel) == 8
    assert tavily_cli._effective_concurrency(serial) == 1


def test_batch_query_request_uses_per_query_value() -> None:
    args = _parse_search(["alpha", "beta"])
    request = tavily_cli._build_search_request(args, "beta")

    assert request["query"] == "beta"
    assert request["search_depth"] == "advanced"
    assert request["max_results"] == 6
    assert request["include_raw_content"] == "markdown"


def test_run_search_batch_writes_one_file_per_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(tavily_cli._OUTPUT_DIR_ENV, str(tmp_path))
    args = _parse_search(["first query", "second query"])
    client = StubClient()

    envelope, exit_code = tavily_cli.run_search_batch(client, args)

    assert exit_code == 0
    assert envelope["command"] == "search"
    assert envelope["output_mode"] == "batch"
    assert envelope["output_dir"] == str(tavily_cli.get_default_output_dir())
    assert envelope["status"] == "ok"
    assert envelope["summary"] == {
        "query_count": 2,
        "success_count": 2,
        "failed_count": 0,
        "credits_used": None,
    }
    assert envelope["input"]["queries"] == ["first query", "second query"]
    assert envelope["input"]["concurrency"] == 4
    assert envelope["input"]["serial"] is False
    assert envelope["input"]["search_depth"] == "advanced"
    assert envelope["input"]["max_results"] == 6
    assert envelope["input"]["raw_content"] == "markdown"
    assert len(client.search_calls) == 2
    assert sorted(call["query"] for call in client.search_calls) == ["first query", "second query"]

    for entry in envelope["results"]:
        output_path = Path(entry["output_path"])
        assert output_path.exists()
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload["command"] == "search"
        assert payload["input"]["query"] == entry["query"]
        assert entry["summary"]["result_count"] == 1
        assert entry["error"] is None


def test_run_search_batch_appends_index_on_name_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(tavily_cli._OUTPUT_DIR_ENV, str(tmp_path))
    args = _parse_search(["same query", "same query"])
    client = StubClient()

    envelope, _ = tavily_cli.run_search_batch(client, args)

    paths = [entry["output_path"] for entry in envelope["results"]]
    assert len(set(paths)) == 2
    assert all(Path(path).exists() for path in paths)


def test_run_search_batch_runs_parallel_faster_than_serial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(tavily_cli._OUTPUT_DIR_ENV, str(tmp_path))
    queries = ["q1", "q2", "q3", "q4"]
    delay = 0.5

    serial_args = _parse_search(queries, "--serial")
    parallel_args = _parse_search(queries, "--concurrency", "4")

    started = time.monotonic()
    tavily_cli.run_search_batch(SlowStubClient(delay=delay), serial_args)
    serial_elapsed = time.monotonic() - started

    started = time.monotonic()
    tavily_cli.run_search_batch(SlowStubClient(delay=delay), parallel_args)
    parallel_elapsed = time.monotonic() - started

    assert serial_elapsed > len(queries) * delay * 0.9
    assert parallel_elapsed < serial_elapsed - delay
    assert parallel_elapsed < serial_elapsed * 0.75


def test_main_batch_success_emits_single_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(tavily_cli._OUTPUT_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(tavily_cli, "_build_client", lambda: StubClient())

    exit_code = tavily_cli.main(["search", "--query", "a", "--query", "b"])

    captured = capsys.readouterr()
    envelope = json.loads(captured.out)
    assert exit_code == 0
    assert envelope["output_mode"] == "batch"
    assert envelope["status"] == "ok"
    assert envelope["summary"]["query_count"] == 2
    assert envelope["summary"]["success_count"] == 2
    assert "mode" not in envelope
    assert "error_count" not in envelope["summary"]
    assert captured.err == ""


def test_main_batch_partial_failure_returns_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(tavily_cli._OUTPUT_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(
        tavily_cli,
        "_build_client",
        lambda: SlowStubClient(delay=0.0, fail_queries={"bad"}),
    )

    exit_code = tavily_cli.main(["search", "--query", "good", "--query", "bad"])

    captured = capsys.readouterr()
    envelope = json.loads(captured.out)
    assert exit_code == 0
    assert envelope["status"] == "partial"
    assert envelope["summary"]["success_count"] == 1
    assert envelope["summary"]["failed_count"] == 1

    good = next(entry for entry in envelope["results"] if entry["query"] == "good")
    bad = next(entry for entry in envelope["results"] if entry["query"] == "bad")
    assert Path(good["output_path"]).exists()
    assert bad["output_path"] is None
    assert bad["summary"] is None
    assert bad["error"]["http_status"] is None
    assert bad["error"]["error"] == "boom: bad"
    assert "Warning" in captured.err


def test_main_batch_all_failures_return_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(tavily_cli._OUTPUT_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(
        tavily_cli,
        "_build_client",
        lambda: SlowStubClient(delay=0.0, fail_queries={"a", "b"}),
    )

    exit_code = tavily_cli.main(["search", "--query", "a", "--query", "b"])

    captured = capsys.readouterr()
    envelope = json.loads(captured.out)
    assert exit_code == 1
    assert envelope["status"] == "error"
    assert envelope["summary"]["success_count"] == 0
    assert envelope["summary"]["failed_count"] == 2
    assert "Warning" in captured.err


def test_main_single_mode_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(tavily_cli._OUTPUT_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(tavily_cli, "_build_client", lambda: StubClient())

    exit_code = tavily_cli.main(["search", "latest ai"])

    captured = capsys.readouterr()
    status_payload = json.loads(captured.out)
    assert exit_code == 0
    assert status_payload["command"] == "search"
    assert status_payload["output_mode"] == "file"
    assert "mode" not in status_payload
    assert Path(status_payload["output_path"]).exists()


def test_main_usage_error_exits_two() -> None:
    with pytest.raises(SystemExit) as excinfo:
        tavily_cli.main(["search"])

    assert excinfo.value.code == 2


def test_main_batch_keyboard_interrupt_returns_130(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(tavily_cli, "_build_client", lambda: StubClient())

    def interrupt(client: object, args: object) -> object:
        raise KeyboardInterrupt

    monkeypatch.setattr(tavily_cli, "run_search_batch", interrupt)

    exit_code = tavily_cli.main(["search", "--query", "a"])

    captured = capsys.readouterr()
    assert exit_code == 130
    assert "Interrupted" in captured.err
