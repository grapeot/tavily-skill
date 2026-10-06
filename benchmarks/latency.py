#!/usr/bin/env python3
"""Latency benchmark for the tavily-skill CLI.

Compares three execution patterns using REAL API calls:

    standalone       N separate `python -m tavily_skill search "<q>"` processes
    batch-parallel   ONE process with N `--query` flags, thread-pool parallelism
    batch-serial     ONE process with N `--query` flags plus `--serial`

The hypothesis under test: batch mode wins because each standalone process
re-pays a fixed cost (interpreter start, TLS handshake, credential resolution
including the optional `op read`) and because N serial API waits collapse into
one parallel wave.

Opt-in only. Set `RUN_TAVILY_LATENCY=1` to spend real credits; otherwise the
script prints a skip note and exits 0 so CI and offline runs never bill anyone.

The API key is never read, printed, logged, or persisted here. Child processes
resolve credentials exactly the way the CLI always does. Children run from the
repository root so the local `.env` is discovered, and every child is pointed at
a temporary `TAVILY_CLI_OUTPUT_DIR` so the benchmark never pollutes the real
snapshot corpus. This module shells out, so it uses only the standard library.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

OUTPUT_DIR_ENV = "TAVILY_CLI_OUTPUT_DIR"
GATE_ENV = "RUN_TAVILY_LATENCY"
SKIP_MESSAGE = "skipped (set RUN_TAVILY_LATENCY=1; spends real credits)"

DEFAULT_QUERIES = 4
DEFAULT_REPEATS = 3
DEFAULT_CONCURRENCY = 4
DEFAULT_MAX_RESULTS = 3

MODE_STANDALONE = "standalone"
MODE_PARALLEL = "batch-parallel"
MODE_SERIAL = "batch-serial"
MODES = (MODE_STANDALONE, MODE_PARALLEL, MODE_SERIAL)

# Topic pool used to synthesize the requested number of unique queries. Uniqueness
# comes from a per-run suffix, so provider-side caching cannot contaminate results.
_BASE_QUERIES: tuple[str, ...] = (
    "tavily api latency benchmark",
    "agent web search tooling",
    "python subprocess overhead",
    "parallel http request patterns",
    "search api concurrency limits",
    "web content extraction pipelines",
    "llm agent retrieval research",
    "cloud api cold start",
)


def gate_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return True only when the caller explicitly opted into spending credits."""
    source = os.environ if env is None else env
    return source.get(GATE_ENV) == "1"


def unique_suffix() -> str:
    """Short, unique, non-secret token appended to every query in one run."""
    return uuid.uuid4().hex[:8]


def make_queries(
    count: int,
    suffix_factory: Callable[[], str] = unique_suffix,
    base_queries: Sequence[str] | None = None,
) -> list[str]:
    """Build `count` unique queries, each carrying one shared run suffix."""
    if count < 1:
        raise ValueError("count must be at least 1")
    pool = list(base_queries) if base_queries else list(_BASE_QUERIES)
    if not pool:
        raise ValueError("base_queries must not be empty")
    suffix = suffix_factory()
    return [f"{pool[i % len(pool)]} {suffix}-{i}" for i in range(count)]


def median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("median requires at least one value")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def compute_speedup(baseline_seconds: float, optimized_seconds: float) -> float:
    """Speedup of `optimized` over `baseline`; >1 means optimized is faster."""
    if optimized_seconds <= 0:
        raise ValueError("optimized_seconds must be positive")
    return baseline_seconds / optimized_seconds


def build_standalone_command(
    python_executable: str,
    query: str,
    max_results: int,
) -> list[str]:
    return [
        python_executable,
        "-m",
        "tavily_skill",
        "search",
        query,
        "--max-results",
        str(max_results),
    ]


def build_batch_command(
    python_executable: str,
    queries: Sequence[str],
    max_results: int,
    concurrency: int,
    serial: bool = False,
) -> list[str]:
    command = [python_executable, "-m", "tavily_skill", "search"]
    for query in queries:
        command += ["--query", query]
    command += ["--max-results", str(max_results), "--concurrency", str(concurrency)]
    if serial:
        command.append("--serial")
    return command


def build_child_env(base_env: Mapping[str, str], output_dir: os.PathLike[str] | str) -> dict[str, str]:
    """Copy an environment, isolate the output corpus, and make `src` importable."""
    env = dict(base_env)
    env[OUTPUT_DIR_ENV] = str(output_dir)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(
        [str(SRC_ROOT)] + ([existing] if existing else [])
    )
    return env


def time_command(
    command: Sequence[str],
    env: Mapping[str, str],
    cwd: os.PathLike[str] | str,
    runner: Callable[..., object] | None = None,
) -> float:
    """Wall-clock one subprocess with `perf_counter`; resolved runner is mockable."""
    run = subprocess.run if runner is None else runner
    started = time.perf_counter()
    run(list(command), capture_output=True, text=True, env=dict(env), cwd=str(cwd))
    return time.perf_counter() - started


def run_mode(
    mode: str,
    *,
    python_executable: str,
    queries: Sequence[str],
    repeats: int,
    concurrency: int,
    max_results: int,
    env: Mapping[str, str],
    cwd: os.PathLike[str] | str,
    runner: Callable[..., object] | None = None,
) -> list[float]:
    """Time one mode `repeats` times and return the per-repeat wall clocks."""
    times: list[float] = []
    for _ in range(repeats):
        if mode == MODE_STANDALONE:
            total = 0.0
            for query in queries:
                total += time_command(
                    build_standalone_command(python_executable, query, max_results),
                    env,
                    cwd,
                    runner,
                )
            times.append(total)
        elif mode == MODE_PARALLEL:
            times.append(
                time_command(
                    build_batch_command(
                        python_executable, queries, max_results, concurrency, serial=False
                    ),
                    env,
                    cwd,
                    runner,
                )
            )
        elif mode == MODE_SERIAL:
            times.append(
                time_command(
                    build_batch_command(
                        python_executable, queries, max_results, concurrency, serial=True
                    ),
                    env,
                    cwd,
                    runner,
                )
            )
        else:
            raise ValueError(f"unknown mode: {mode}")
    return times


def shape_report(
    times_by_mode: Mapping[str, Sequence[float]],
    *,
    queries: int,
    repeats: int,
    concurrency: int,
    max_results: int,
) -> dict[str, object]:
    modes: dict[str, object] = {}
    for mode in MODES:
        values = list(times_by_mode[mode])
        modes[mode] = {
            "times": [round(value, 4) for value in values],
            "median_seconds": round(median(values), 4),
            "min_seconds": round(min(values), 4),
            "max_seconds": round(max(values), 4),
        }
    standalone = modes[MODE_STANDALONE]["median_seconds"]  # type: ignore[index]
    parallel = modes[MODE_PARALLEL]["median_seconds"]  # type: ignore[index]
    serial = modes[MODE_SERIAL]["median_seconds"]  # type: ignore[index]
    return {
        "queries": queries,
        "repeats": repeats,
        "concurrency": concurrency,
        "max_results": max_results,
        "modes": modes,
        "speedup": {
            "parallel_vs_standalone": (
                round(compute_speedup(standalone, parallel), 3) if parallel > 0 else None
            ),
            "serial_vs_standalone": (
                round(compute_speedup(standalone, serial), 3) if serial > 0 else None
            ),
        },
    }


def format_table(report: Mapping[str, object]) -> str:
    lines = [
        "Tavily latency benchmark",
        (
            f"queries={report['queries']} repeats={report['repeats']} "
            f"concurrency={report['concurrency']} max_results={report['max_results']}"
        ),
        "",
        f"{'mode':<16}{'median(s)':>12}{'min(s)':>10}{'max(s)':>10}",
    ]
    modes = report["modes"]  # type: ignore[assignment]
    for mode in MODES:
        data = modes[mode]  # type: ignore[index]
        lines.append(
            f"{mode:<16}{data['median_seconds']:>12.3f}"
            f"{data['min_seconds']:>10.3f}{data['max_seconds']:>10.3f}"
        )
    speedup = report["speedup"]  # type: ignore[assignment]
    parallel = speedup.get("parallel_vs_standalone")  # type: ignore[union-attr]
    serial = speedup.get("serial_vs_standalone")  # type: ignore[union-attr]
    lines.append("")
    lines.append(
        f"speedup (batch-parallel vs standalone): {parallel:.2f}x"
        if parallel is not None
        else "speedup (batch-parallel vs standalone): n/a"
    )
    lines.append(
        f"speedup (batch-serial vs standalone):   {serial:.2f}x"
        if serial is not None
        else "speedup (batch-serial vs standalone): n/a"
    )
    return "\n".join(lines)


def _collect(
    *,
    python_executable: str,
    queries: Sequence[str],
    repeats: int,
    concurrency: int,
    max_results: int,
    env: Mapping[str, str],
    runner: Callable[..., object] | None = None,
) -> dict[str, object]:
    times_by_mode: dict[str, list[float]] = {}
    for mode in MODES:
        times_by_mode[mode] = run_mode(
            mode,
            python_executable=python_executable,
            queries=queries,
            repeats=repeats,
            concurrency=concurrency,
            max_results=max_results,
            env=env,
            cwd=REPO_ROOT,
            runner=runner,
        )
    return shape_report(
        times_by_mode,
        queries=len(queries),
        repeats=repeats,
        concurrency=concurrency,
        max_results=max_results,
    )


def run_benchmark(
    *,
    python_executable: str,
    queries: Sequence[str],
    repeats: int,
    concurrency: int,
    max_results: int,
    base_env: Mapping[str, str] | None = None,
    output_root: os.PathLike[str] | str | None = None,
    runner: Callable[..., object] | None = None,
) -> dict[str, object]:
    """Run every mode and return the shaped report.

    With `output_root=None`, a fresh temporary directory isolates the corpus and
    is removed afterwards. `output_root` exists mainly so callers can inspect it.
    """
    base = dict(os.environ if base_env is None else base_env)
    if output_root is not None:
        env = build_child_env(base, output_root)
        return _collect(
            python_executable=python_executable,
            queries=queries,
            repeats=repeats,
            concurrency=concurrency,
            max_results=max_results,
            env=env,
            runner=runner,
        )
    with tempfile.TemporaryDirectory(prefix="tavily_latency_") as tmp:
        env = build_child_env(base, tmp)
        return _collect(
            python_executable=python_executable,
            queries=queries,
            repeats=repeats,
            concurrency=concurrency,
            max_results=max_results,
            env=env,
            runner=runner,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="latency-benchmark",
        description="Compare standalone vs batch Tavily search latency (opt-in, spends credits).",
    )
    parser.add_argument("--queries", type=int, default=DEFAULT_QUERIES, help="Queries per run")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS, help="Repeats per mode")
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Batch parallelism"
    )
    parser.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS, help="Results per query")
    parser.add_argument("--json-out", default=None, help="Optional path to write the JSON report")
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.queries < 1:
        parser.error("--queries must be at least 1.")
    if args.repeats < 1:
        parser.error("--repeats must be at least 1.")
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1.")
    if not 1 <= args.max_results <= 20:
        parser.error("--max-results must be between 1 and 20.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(parser, args)

    if not gate_enabled():
        print(SKIP_MESSAGE)
        return 0

    queries = make_queries(args.queries)
    report = run_benchmark(
        python_executable=sys.executable,
        queries=queries,
        repeats=args.repeats,
        concurrency=args.concurrency,
        max_results=args.max_results,
    )
    print(format_table(report))

    if args.json_out:
        path = Path(args.json_out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
