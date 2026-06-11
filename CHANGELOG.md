# Changelog

## 1.1.3 - 2026-06-10 - Pre-release accuracy fixes

### Fixed
- Engine versions in `data/README.md` corrected to match the paper:
  **vLLM 0.19.0 / SGLang 0.5.10** (were 0.11.0 / 0.5.5).
- `data/README.md` rps sweep corrected to `{1, 5, 10, 25, 50, 100, 200}` (the
  actual CSV values), and the `hardware` / `architecture` enums to match the
  corpus (`A100_80GB_PCIe`; `sparse_moe` / `ultra_sparse_moe`).
- `compute_c_eff` now returns `None` for non-positive throughput, and the
  rolling-rate helper drops counter-reset (`v1 < v0`) samples — a server
  restart can no longer surface a negative $/MTok.
- Partial CLI overrides (e.g. only `--tensor-parallel-size`) now overlay on the
  auto-detected config instead of forcing `model_id="unknown"`.

### Docs
- README reference-panel note clarifies the catalog match keys on
  model + quantization + GPU-count only (not engine or GPU model).
- system-design `/cost` field count corrected (26, not 28).

## 1.1.2 - 2026-06-10 - Public release

### Added
- `reference_paper` in `benchmark_curves.yaml` and `[project.urls]` in
  `pyproject.toml` now point at the published preprint
  [arXiv:2606.11690](https://arxiv.org/abs/2606.11690), closing the two
  placeholders noted in 1.1.1.

### Changed
- README and catalog header updated to the published paper title,
  "A Concurrency-Aware Methodology for LLM Infrastructure Cost Estimation."

## 1.1.1 - 2026-04-29 - Cyber-prep hardening

### Changed
- **Default bind address is now `127.0.0.1`** (was `0.0.0.0`). Pass
  `--bind 0.0.0.0` explicitly to expose the `/cost` and `/metrics` endpoints
  to other hosts on the network. The startup banner now warns when the
  meter is bound externally.
- `--gpu-hourly-cost`, `--n-gpus`, `--window`, `--port`,
  `--tensor-parallel-size`, and the `--slo-*-ms` flags now reject negative,
  zero, NaN, and Inf values at parse time with a clear error message.
- `--quantization` is validated against `{float16, fp8, int8, int4}`.
- `__version__` is now sourced from package metadata (single source of
  truth in `pyproject.toml`); previously the in-package literal had drifted
  to `0.1.0` while the wheel reported `1.1.0`.
- Scraper docstring now correctly describes percentile readout as
  "conservative upper-bound bucket lookup" (no linear interpolation).
- `CostSnapshot.to_dict()` distinguishes a true `0.0` reading from a
  missing measurement; previously both were collapsed to `null`.

### Removed
- Pre-1.0 demo logs and 7-column demo CSVs that still carried the
  retracted "waste" / "underutilization penalty" framing and exposed
  HuggingFace cache layout strings. The catalog and `data/README.md`
  remain as the canonical documentation surface.
- Placeholder `reference_paper: arxiv.org/abs/XXXX.XXXXX` from
  `benchmark_curves.yaml`. Will be re-added with the real arXiv ID.
- Project URLs in `pyproject.toml` pointing at a non-existent GitHub
  repo. Will be re-added once the public mirror is live.

### Added
- `[project.optional-dependencies]` declaring `dev = ["pytest>=8"]` so
  `pip install -e ".[dev]"` makes the test suite runnable.
- `--version` / `-V` flag.
- SIGTERM handler so `--log-csv` writers flush cleanly under systemd
  / Kubernetes shutdown.

### Fixed
- Schema column count in `data/README.md` (was "27 columns", actual is 26).
- Casing of the README "Disclosure" section reference in 1.1.0 changelog
  entry below.

## 1.1.0 - 2026-04-23 - Cross-hardware catalog + raw corpus

### Added
- **8 A100-80GB curves** in `benchmark_curves.yaml` (A1-A4 vLLM, AS1 SGLang,
  M1-M3 Mixtral multi-GPU), from the paper's §5.8 cross-hardware validation.
  Brings the shipped catalog to **20 reference curves** (12 H100 + 8 A100).
- `data/` directory with frozen per-run CSVs that every catalog value is
  derived from: `master_results.csv` (140 runs), `master_results_v2.csv`
  (32 extended-workload runs), `c2_stability_cv.csv` (3-replicate CVs).
  Schema and re-derivation snippet in `data/README.md`.
- `Disclosure` section in README clarifying independent-research status.

### Notes
- The cross-hardware finding: framework's qualitative structure (8-12x C_eff
  spread driven by lambda; engine ordering) holds on A100 too. Absolute
  theta_max values differ (A100 is slower, cheaper); the underutilisation
  penalty pattern is identical. See paper §5.8 for the full analysis.

## 1.0.0 - 2026-04-16 - Objective meter release

### Breaking changes
- Removed `saturation_cost_per_mtok`, `utilization_pct`, `penalty_multiplier` from
  `/cost` JSON and `/metrics` Prometheus output. These derived "waste" judgements
  were misleading without the user's SLO context.
- CSV log columns have changed. Rows produced by 0.x are not compatible with 1.0
  readers; keep a separate file.
- `--compare-api` now requires `--accept-slo-mismatch` and prints a banner before
  the comparison table. The comparison math is unchanged.

### Added
- Full vLLM `/metrics` ingestion: TTFT/TPOT/E2E histograms (p50/p90/p99),
  prompt/gen length histograms, arrival rate lambda, batch state (running/waiting/
  swapped), KV-cache utilization.
- `--slo-ttft-p99-ms`, `--slo-tpot-p99-ms`, `--slo-e2el-p99-ms` flags. When set,
  meter prints an observed-vs-budget status line. No derived "headroom" number.
- `LiveTelemetry` dataclass decoupling metric ingestion from cost math.
- `CatalogReference` neutral reference panel showing `theta_max_tok_s` alongside
  the exact `workload_protocol` under which it was measured.
- 6 new SGLang curves in `benchmark_curves.yaml` (S1-S6 from paper).
- `workload_protocol` block per catalog curve.

### Paper anchor
The headline 24-36x cost-variation finding is visible live as C_eff swings across
lambda without any editorialising from the tool.

## 0.1.0 - 2026-04-04
Initial release (pre-paper). Contained waste/penalty framing - retracted in 1.0.
