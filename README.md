# vllm-cost-meter

**Objective live telemetry + effective cost-per-million-tokens meter for vLLM servers.**

Paper-backed companion to:
> *Beyond Per-Token Pricing: A Concurrency-Aware Methodology for LLM Infrastructure Cost Estimation*

## What it is (v1 - objective)

A read-only observer of a running vLLM server. Ingests the full Prometheus `/metrics`
surface (throughput, arrival rate, TTFT/TPOT/E2E histograms, prompt/gen length,
batch state, KV cache) and surfaces live `C_eff = f(H, M, Q, lambda, L)` from the paper.

**What this tool does NOT do:**
- It does **not** claim you are "wasting X%." That framing requires your workload's
  SLO context, which only you can supply.
- It does **not** derive a "max throughput you could reach" - goodput curves belong
  to a v2 calibration mode, not this release.
- It does **not** compare your cost to serverless APIs unless you explicitly accept
  the SLO mismatch (serverless pricing is unconditioned on TTFT/TPOT SLOs).

## Quick start

```bash
pip install -e .

# Minimum
vllm-cost-meter --gpu-hourly-cost 6.98

# With SLO budgets - meter shows observed vs budget
vllm-cost-meter --gpu-hourly-cost 6.98 \
  --slo-ttft-p99-ms 300 --slo-tpot-p99-ms 50 --slo-e2el-p99-ms 5000

# API comparison (requires explicit SLO-mismatch acknowledgement)
vllm-cost-meter --gpu-hourly-cost 6.98 --compare-api --accept-slo-mismatch

# Expose /cost and /metrics on all interfaces (default is 127.0.0.1)
vllm-cost-meter --gpu-hourly-cost 6.98 --bind 0.0.0.0 --port 9090
```

`vllm-cost-meter --help` lists every flag with its valid range.

## Output

Panel of live telemetry (C_eff, throughput, lambda, TTFT/TPOT/E2E percentiles, batch
state, KV cache) followed by:

- A neutral **catalog reference** panel when the detected model + quantization + GPU
  count matches a paper benchmark curve (shows theta_max plus the exact workload protocol
  under which it was measured). The match keys on model, quantization, and GPU count
  only — not engine (vLLM vs SGLang) or GPU model (H100 vs A100) — so if your setup
  differs from the curve shown, treat the reference as indicative rather than exact.
- An **SLO status** line when `--slo-*` flags are set (observed vs declared budget).

## Paper catalog

`vllm_cost_meter/data/benchmark_curves.yaml` ships **20 reference curves** from the paper:

- **12 on H100-80GB** — C1–C6 (vLLM) + S1–S6 (SGLang) across Llama-3.1-8B,
  Qwen3-30B-A3B, Mixtral-8x7B, FP16 and FP8.
- **8 on A100-80GB** (cross-hardware validation, paper §5.8) — A1–A4 (vLLM
  single-GPU), AS1 (SGLang Llama), M1/M2 (2×A100 Mixtral vLLM + SGLang),
  M3 (4×A100 Mixtral vLLM).

Each row declares its `workload_protocol` (I/O shape, arrival pattern, prefix
caching, SLA bound). Community contributions welcome via PR.

## Raw corpus

The `data/` directory ships the **frozen per-run CSVs** that every curve
above is derived from — 140 primary-corpus runs
(`data/master_results.csv`), 32 extended-workload runs
(`data/master_results_v2.csv`), and 3-replicate stability CVs
(`data/c2_stability_cv.csv`). Schema + re-derivation snippet in
[`data/README.md`](data/README.md).

## Prometheus gauges exposed (`/metrics` on port 9090)

`llm_cost_meter_eff_cost_per_mtok`, `llm_cost_meter_tps_observed`,
`llm_cost_meter_tps_input`, `llm_cost_meter_lambda_rps`,
`llm_cost_meter_ttft_{p50,p90,p99}_ms`, `llm_cost_meter_tpot_{p50,p99}_ms`,
`llm_cost_meter_e2el_{p50,p99}_ms`, `llm_cost_meter_prompt_len_p99`,
`llm_cost_meter_gen_len_p99`, `llm_cost_meter_batch_{running,waiting,swapped}`,
`llm_cost_meter_kv_cache_pct`.

Each gauge carries `model`, `quant`, `n_gpus` labels.

## What we deliberately removed in v1

The prior 0.1 release derived "waste" / headroom fields from a saturation
reference curve. Those were misleading without the user's SLO context, and
have been removed. See `CHANGELOG.md` for exact field names and migration notes.

## Companion paper

> Preprint: *Beyond Per-Token Pricing: A Concurrency-Aware Methodology for LLM Infrastructure Cost Estimation* — [arXiv:2606.11690](https://arxiv.org/abs/2606.11690) ([DOI: 10.48550/arXiv.2606.11690](https://doi.org/10.48550/arXiv.2606.11690)). Every numerical claim in §5 of the paper can be re-derived directly from `data/master_results.csv` using the groupby snippet in [`data/README.md`](data/README.md).

## Disclosure

This project is independent research by the author. It is not affiliated
with, endorsed by, or reflective of the views of any current or past
employer. No proprietary systems, data, or infrastructure were used. All
benchmark runs were executed on the author's own time using personally
provisioned cloud GPUs.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE).
