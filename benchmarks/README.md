# Latency Benchmark

`latency.py` measures how much the `search` batch mode saves over the
"one process per query" pattern agents used before. It runs **real Tavily API
calls**, so it is opt-in and must never run by default in CI.

## Modes

| Mode | What it runs | What it measures |
|---|---|---|
| `standalone` | N separate `python -m tavily_skill search "<q>"` processes | Today's agent pattern: each query pays its own process start, TLS handshake, and credential resolution |
| `batch-parallel` | ONE `python -m tavily_skill search --query q1 --query q2 ...` invocation | One process, thread-pool parallelism, one parallel wave of API waits |
| `batch-serial` | The same single invocation plus `--serial` | One process, but queries run one after another; isolates the parallel-wave effect from the process-reuse effect |

Comparing `batch-parallel` against `standalone` captures both savings.
Comparing `batch-serial` against `standalone` captures the process/credential
reuse alone (same number of serial API waits, fewer process startups).

## How to run

```bash
RUN_TAVILY_LATENCY=1 .venv/bin/python benchmarks/latency.py
RUN_TAVILY_LATENCY=1 .venv/bin/python benchmarks/latency.py --queries 6 --repeats 3 --concurrency 4
RUN_TAVILY_LATENCY=1 .venv/bin/python benchmarks/latency.py --json-out tmp/bench.json
```

Run it from the repository root. Children also run from the repository root so
the local `.env` is found the same way a normal CLI call finds it.

With `RUN_TAVILY_LATENCY` unset the script prints
`skipped (set RUN_TAVILY_LATENCY=1; spends real credits)` and exits 0. CI stays
free.

Arguments: `--queries` (default 4), `--repeats` (default 3), `--concurrency`
(default 4), `--max-results` (default 3), `--json-out PATH` (optional).

## What it reports

For each mode it prints min / median / max wall-clock seconds and two speedups:

- `batch-parallel vs standalone`
- `batch-serial vs standalone`

The speedup uses medians: `median(standalone total) / median(batch-parallel
single invocation)`. A value near `N` means the N queries effectively collapsed
into one; a value near `1` means batch mode did not help (for example when a
single query dominates and the queries were already independent).

## Methodology notes

- **Unique queries per run.** Every query gets a short random suffix so
  provider-side caching cannot make a warm batch look artificially fast. This
  was a real trap: reusing identical queries made a "hot cache" batch read
  faster than a single cold call.
- **Isolated corpus.** Children get a temporary `TAVILY_CLI_OUTPUT_DIR`, so the
  benchmark never writes into the real snapshot corpus.
- **Wall clock.** Time is measured with `time.perf_counter()` around
  `subprocess.run`, which is what an agent actually waits for.
- **No secrets.** The benchmark never reads, prints, logs, or persists the API
  key. It does not read `.env`; the child CLI resolves credentials on its own.

## Caveats

- **Network variance.** Absolute seconds move with connection quality, provider
  load, and machine state. Trust the ratio, not the raw numbers.
- **Provider caching.** Even with unique suffixes, repeated structural queries
  may hit provider-side caches. Treat small deltas as noise.
- **Cold vs warm.** The first run of a process pays extra import and connection
  setup. The median over `--repeats` is more stable than any single run.
- **Cost.** Each query is one paid search. `queries * (2 * repeats + repeats)`
  calls is a rough upper bound for a full run; start small.
- **Failure handling.** A failed child still contributes its (short) wall time.
  Verify credentials work with a single manual search before trusting a report.

## Suggested baseline

```bash
# 4 queries, 3 repeats: 4 standalone + 4 parallel + 4 serial per repeat
RUN_TAVILY_LATENCY=1 .venv/bin/python benchmarks/latency.py --queries 4 --repeats 3
```

Read the `batch-parallel vs standalone` line first. Compare it against
`batch-serial vs standalone` to see how much of the gain comes from collapsing
the API waits versus reusing one process and one credential resolution.
