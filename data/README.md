# Benchmark data snapshot

This directory is a **frozen snapshot** of the raw per-run measurements that
back every curve in `vllm_cost_meter/data/benchmark_curves.yaml` and every
figure in the companion paper. Reviewers can re-derive saturation points,
C_eff spreads, and stability CVs directly from these CSVs.

## Files

### `master_results.csv` (140 rows, primary corpus)

Every run in the paper's main corpus: 84 on H100-80GB + 56 on A100-80GB,
across 3 models (Llama-3.1-8B, Qwen3-30B-A3B, Mixtral-8x7B), two precisions
(FP16, FP8 where supported), two engines (vLLM 0.19.0, SGLang 0.5.10), and
concurrency sweeps at rps ∈ {1, 5, 10, 25, 50, 100, 200} where reachable.

Config prefixes:
- `C1..C6` — H100 vLLM configurations
- `S1..S6` — H100 SGLang configurations
- `A1..A4` — A100 vLLM single-GPU configurations
- `AS1`    — A100 SGLang Llama-FP16
- `M1..M3` — A100 Mixtral cross-hardware (2×A100 vLLM, 2×A100 SGLang, 4×A100 vLLM)

**Schema** (26 columns):

| column | units | meaning |
|---|---|---|
| `config` | — | Configuration ID (C1..C6, S1..S6, A1..A4, AS1, M1..M3) |
| `engine` | — | `vllm` or `sglang` |
| `model` | — | HuggingFace model ID |
| `architecture` | — | `dense`, `sparse_moe`, or `ultra_sparse_moe` |
| `active_params` | — | Declared parameter count (display-only) |
| `precision` | — | `float16`, `fp8` |
| `hardware` | — | `H100` or `A100_80GB_PCIe` |
| `gpus` | count | Tensor-parallel GPU count |
| `rps` | req/s | Target arrival rate (λ) for this run |
| `request_throughput` | req/s | Observed completion rate |
| `tps_output` | tok/s | Observed output token throughput |
| `ttft_mean_ms` | ms | Time-to-first-token mean |
| `ttft_p50_ms`, `ttft_p90_ms`, `ttft_p99_ms` | ms | TTFT percentiles |
| `e2el_p50_ms`, `e2el_p90_ms`, `e2el_p99_ms` | ms | End-to-end latency percentiles |
| `tpot_p50_ms`, `tpot_p90_ms` | ms | Time-per-output-token percentiles |
| `gpu_util_pct` | % | nvidia-smi sample-mean utilization |
| `gpu_power_w` | W | nvidia-smi sample-mean power |
| `gpu_cost_hr` | USD/hr | On-demand hourly rate used for C_eff (H100 = 6.98, A100 = 3.67) |
| `c_eff_per_mtok` | USD/Mtok | Effective cost = (gpu_cost_hr × gpus) / (tps_output × 3600/1e6) |
| `c_naive_per_mtok` | USD/Mtok | Floor cost at peak observed throughput for this config |
| `underutil_penalty` | × | c_eff / c_naive — dimensionless penalty from under-concurrency |

### `master_results_v2.csv` (32 rows, extended workload matrix)

Second-tranche runs probing the framework's sensitivity to workload shape
(paper §4 robustness checks). Adds three columns vs `master_results.csv`:

- `io_shape` — `chat` (short-short), `rag` (long-short), `agentic` (long-long)
- `prefix_caching` — `0` or `1` (vLLM `--enable-prefix-caching`)
- `burstiness` — Gamma CV (1.0 = Poisson; 2.0 = bursty)
- `harness_version` — `v2` sentinel

Covers C2 (vLLM Llama-FP8) only; other configs use default I/O shape in the
primary corpus.

### `c2_stability_cv.csv` (4 rows, stability)

Three independent replicates of C2 at λ ∈ {1, 10, 50, 100}. Reports the
coefficient of variation (CV% = σ/μ × 100) for throughput, C_eff, TTFT-p50,
and e2e-p50. Paper §4.2 claims CV < 1% for throughput/C_eff at these rates;
this file is the numeric evidence.

## How the YAML curves map back

Each `theta_max_tok_s` in `benchmark_curves.yaml` is the **maximum**
`tps_output` observed for that `(config, engine, model, precision, hardware,
gpus)` group across the λ sweep in `master_results.csv`. Each
`c_naive_per_mtok` is the corresponding (gpu_cost_hr × gpus) / (θ_max × 3.6).
Re-derive with:

```python
import pandas as pd
df = pd.read_csv("master_results.csv")
sat = df.groupby(["config","engine","model","precision","hardware","gpus"]) \
        .agg(theta_max=("tps_output","max"),
             c_min   =("c_naive_per_mtok","min")).reset_index()
```

## Provenance

Raw per-request JSON logs, server logs, and nvidia-smi traces live in the
companion paper's artifact repository — not shipped here to keep this package
small. Every value in these CSVs has an audit path back to a specific
`vllm bench serve` / `sglang.bench_serving` invocation.
