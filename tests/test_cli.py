from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
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
            "answer": "stub answer",
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
    assert args.answer == "off"
    assert args.raw_content == "markdown"
    assert args.stdout is False


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
        "answer": "answer",
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
    assert payload["data"]["answer"] == "answer"


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
        "data": {"result_count": 1, "image_count": 0, "answer": None},
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
        "data": {"result_count": 2, "image_count": 1, "answer": "yes"},
    }

    tavily_cli._emit_payload(payload, str(output_path))

    captured = capsys.readouterr()
    status_payload = json.loads(captured.out)
    assert status_payload["output_mode"] == "file"
    assert status_payload["output_path"] == str(output_path)
    assert status_payload["summary"]["result_count"] == 2
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
            'answer': 'fake',
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
