# Contributing

Thanks for your interest in `vllm-cost-meter`. Contributions — bug reports,
fixes, docs, and especially new benchmark curves — are welcome.

## Development setup

```bash
git clone https://github.com/pChitral/vllm-cost-meter
cd vllm-cost-meter
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running tests

```bash
pytest
```

CI runs the same suite across Python 3.10–3.12 on every push and pull request.

## Adding a benchmark curve

The reference catalog lives in
[`vllm_cost_meter/data/benchmark_curves.yaml`](vllm_cost_meter/data/benchmark_curves.yaml).
Match the fields and aliasing style of the existing entries, and include the
`engine`, `gpu_type`, `quantization`, and `n_gpus` the curve was measured on.
Every curve must declare its `workload_protocol` (I/O shape, arrival pattern,
prefix caching, SLA bound) so consumers can judge applicability.

## Pull requests

1. Branch from `main`.
2. Keep changes focused; add or update tests where it makes sense.
3. Make sure `pytest` passes.
4. Open a PR describing what changed and why.

## Scope

This is the v1 **objective** meter: it reports raw cost and neutral catalog
context, and deliberately avoids judgement fields (waste %, headroom) that
require workload- and SLO-specific context the meter cannot infer. PRs that
re-introduce such fields will be asked to gate them behind explicit,
user-supplied SLO inputs.

## License

By contributing you agree that your contributions are licensed under the
project's [MIT License](LICENSE).
