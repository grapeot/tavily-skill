from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCH_PATH = PROJECT_ROOT / "benchmarks" / "latency.py"


def _load_bench():
    spec = importlib.util.spec_from_file_location("bench_latency", BENCH_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bench = _load_bench()


class _FakeCompleted:
    returncode = 0


class _RunSpy:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, command, capture_output=True, text=True, env=None, cwd=None):
        self.calls.append(
            {"command": list(command), "env": dict(env or {}), "cwd": cwd}
        )
        return _FakeCompleted()


def test_parser_defaults() -> None:
    args = bench.build_parser().parse_args([])

    assert args.queries == 4
    assert args.repeats == 3
    assert args.concurrency == 4
    assert args.max_results == 3
    assert args.json_out is None


def test_parser_overrides() -> None:
    args = bench.build_parser().parse_args(
        ["--queries", "6", "--repeats", "2", "--concurrency", "8", "--max-results", "5", "--json-out", "/tmp/x.json"]
    )

    assert args.queries == 6
    assert args.repeats == 2
    assert args.concurrency == 8
    assert args.max_results == 5
    assert args.json_out == "/tmp/x.json"


@pytest.mark.parametrize(
    "argv",
    [
        ["--queries", "0"],
        ["--repeats", "0"],
        ["--concurrency", "0"],
        ["--max-results", "0"],
        ["--max-results", "21"],
    ],
)
def test_validate_args_rejects_bad_values(argv: list[str]) -> None:
    parser = bench.build_parser()
    args = parser.parse_args(argv)

    with pytest.raises(SystemExit):
        bench.validate_args(parser, args)


def test_gate_enabled() -> None:
    assert bench.gate_enabled({bench.GATE_ENV: "1"}) is True
    assert bench.gate_enabled({bench.GATE_ENV: "0"}) is False
    assert bench.gate_enabled({}) is False


def test_make_queries_unique_and_counted() -> None:
    queries = bench.make_queries(5, suffix_factory=lambda: "aben1234")

    assert len(queries) == 5
    assert len(set(queries)) == 5
    assert all("aben1234" in query for query in queries)


def test_make_queries_cycles_pool_without_collision() -> None:
    pool = ["alpha", "beta"]
    queries = bench.make_queries(4, suffix_factory=lambda: "s", base_queries=pool)

    assert len(set(queries)) == 4
    assert all(query.startswith(("alpha ", "beta ")) for query in queries)


def test_make_queries_rejects_nonpositive() -> None:
    with pytest.raises(ValueError):
        bench.make_queries(0)


def test_median_odd_even() -> None:
    assert bench.median([3.0, 1.0, 2.0]) == 2.0
    assert bench.median([1.0, 2.0, 3.0, 4.0]) == 2.5


def test_median_rejects_empty() -> None:
    with pytest.raises(ValueError):
        bench.median([])


def test_compute_speedup() -> None:
    assert bench.compute_speedup(12.0, 4.0) == 3.0


def test_compute_speedup_rejects_nonpositive_denominator() -> None:
    with pytest.raises(ValueError):
        bench.compute_speedup(1.0, 0.0)


def test_build_standalone_command() -> None:
    command = bench.build_standalone_command("/venv/bin/python", "hello world", 3)

    assert command == [
        "/venv/bin/python",
        "-m",
        "tavily_skill",
        "search",
        "hello world",
        "--max-results",
        "3",
    ]


def test_build_batch_command_parallel() -> None:
    command = bench.build_batch_command("/venv/bin/python", ["q1", "q2"], 3, 4, serial=False)

    assert command == [
        "/venv/bin/python",
        "-m",
        "tavily_skill",
        "search",
        "--query",
        "q1",
        "--query",
        "q2",
        "--max-results",
        "3",
        "--concurrency",
        "4",
    ]


def test_build_batch_command_serial_appends_flag() -> None:
    command = bench.build_batch_command("/venv/bin/python", ["q1"], 3, 4, serial=True)

    assert command[-1] == "--serial"


def test_build_child_env_sets_output_dir_and_pythonpath() -> None:
    env = bench.build_child_env({"PATH": "/usr/bin"}, "/tmp/corpus")

    assert env[bench.OUTPUT_DIR_ENV] == "/tmp/corpus"
    assert str(bench.SRC_ROOT) in env["PYTHONPATH"]


def test_time_command_uses_injected_runner() -> None:
    spy = _RunSpy()

    elapsed = bench.time_command(["echo", "hi"], {"A": "1"}, PROJECT_ROOT, runner=spy)

    assert elapsed >= 0
    assert spy.calls[0]["command"] == ["echo", "hi"]
    assert spy.calls[0]["env"] == {"A": "1"}


def test_run_mode_standalone_counts_one_process_per_query() -> None:
    spy = _RunSpy()

    times = bench.run_mode(
        bench.MODE_STANDALONE,
        python_executable="/venv/bin/python",
        queries=["q1", "q2", "q3"],
        repeats=2,
        concurrency=4,
        max_results=3,
        env={},
        cwd=PROJECT_ROOT,
        runner=spy,
    )

    assert len(times) == 2
    assert len(spy.calls) == 6
    assert all(call["command"][3] == "search" for call in spy.calls)


def test_run_mode_parallel_one_process_per_repeat() -> None:
    spy = _RunSpy()

    bench.run_mode(
        bench.MODE_PARALLEL,
        python_executable="/venv/bin/python",
        queries=["q1", "q2"],
        repeats=3,
        concurrency=4,
        max_results=3,
        env={},
        cwd=PROJECT_ROOT,
        runner=spy,
    )

    assert len(spy.calls) == 3
    assert all("--query" in call["command"] for call in spy.calls)
    assert all("--serial" not in call["command"] for call in spy.calls)


def test_run_mode_serial_sets_serial_flag() -> None:
    spy = _RunSpy()

    bench.run_mode(
        bench.MODE_SERIAL,
        python_executable="/venv/bin/python",
        queries=["q1"],
        repeats=1,
        concurrency=4,
        max_results=3,
        env={},
        cwd=PROJECT_ROOT,
        runner=spy,
    )

    assert spy.calls[0]["command"][-1] == "--serial"


def test_shape_report_computes_speedups() -> None:
    report = bench.shape_report(
        {
            bench.MODE_STANDALONE: [12.0, 12.0, 12.0],
            bench.MODE_PARALLEL: [4.0, 4.0, 4.0],
            bench.MODE_SERIAL: [10.0, 10.0, 10.0],
        },
        queries=4,
        repeats=3,
        concurrency=4,
        max_results=3,
    )

    assert report["modes"][bench.MODE_STANDALONE]["median_seconds"] == 12.0
    assert report["modes"][bench.MODE_PARALLEL]["median_seconds"] == 4.0
    assert report["speedup"]["parallel_vs_standalone"] == 3.0
    assert report["speedup"]["serial_vs_standalone"] == 1.2


def test_shape_report_handles_zero_denominator() -> None:
    report = bench.shape_report(
        {
            bench.MODE_STANDALONE: [5.0],
            bench.MODE_PARALLEL: [0.0],
            bench.MODE_SERIAL: [5.0],
        },
        queries=1,
        repeats=1,
        concurrency=1,
        max_results=1,
    )

    assert report["speedup"]["parallel_vs_standalone"] is None


def test_format_table_contains_modes_and_speedup() -> None:
    report = bench.shape_report(
        {
            bench.MODE_STANDALONE: [12.0],
            bench.MODE_PARALLEL: [4.0],
            bench.MODE_SERIAL: [10.0],
        },
        queries=4,
        repeats=1,
        concurrency=4,
        max_results=3,
    )

    table = bench.format_table(report)

    assert "standalone" in table
    assert "batch-parallel" in table
    assert "batch-serial" in table
    assert "3.00x" in table


def test_run_benchmark_mocks_subprocess_and_isolates_output(tmp_path: Path) -> None:
    spy = _RunSpy()

    report = bench.run_benchmark(
        python_executable="/venv/bin/python",
        queries=["q1", "q2"],
        repeats=2,
        concurrency=4,
        max_results=3,
        base_env={"PATH": "/usr/bin"},
        output_root=tmp_path,
        runner=spy,
    )

    assert report["queries"] == 2
    assert set(report["modes"]) == set(bench.MODES)
    assert all(call["env"][bench.OUTPUT_DIR_ENV] == str(tmp_path) for call in spy.calls)
    assert len(spy.calls) == 2 * 2 + 2 + 2


def test_main_skips_when_gate_unset(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv(bench.GATE_ENV, raising=False)

    def _explode(*args: object, **kwargs: object) -> object:
        raise AssertionError("subprocess must not run when the gate is unset")

    monkeypatch.setattr(bench.subprocess, "run", _explode)

    exit_code = bench.main([])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "skipped" in captured.out


def test_main_writes_json_when_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(bench.GATE_ENV, "1")
    fake_report = {
        "queries": 4,
        "repeats": 1,
        "concurrency": 4,
        "max_results": 3,
        "modes": {
            bench.MODE_STANDALONE: {"times": [1.0], "median_seconds": 1.0, "min_seconds": 1.0, "max_seconds": 1.0},
            bench.MODE_PARALLEL: {"times": [1.0], "median_seconds": 1.0, "min_seconds": 1.0, "max_seconds": 1.0},
            bench.MODE_SERIAL: {"times": [1.0], "median_seconds": 1.0, "min_seconds": 1.0, "max_seconds": 1.0},
        },
        "speedup": {"parallel_vs_standalone": 1.0, "serial_vs_standalone": 1.0},
    }
    monkeypatch.setattr(bench, "run_benchmark", lambda **kwargs: fake_report)
    json_path = tmp_path / "report.json"

    exit_code = bench.main(["--repeats", "1", "--json-out", str(json_path)])

    assert exit_code == 0
    written = json.loads(json_path.read_text(encoding="utf-8"))
    assert written["queries"] == 4
    assert "Tavily latency benchmark" in capsys.readouterr().out
