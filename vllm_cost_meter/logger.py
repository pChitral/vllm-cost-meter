# vllm_cost_meter/logger.py
"""CSV logger - one row per scrape tick. Matches objective v1 snapshot schema."""
from __future__ import annotations
import csv
from datetime import datetime, timezone
from pathlib import Path

from vllm_cost_meter.cost import CostSnapshot


class CsvLogger:
    COLUMNS = [
        "timestamp",
        "eff_cost_per_mtok",
        "tps_out", "tps_in", "lambda_rps",
        "ttft_p50_ms", "ttft_p90_ms", "ttft_p99_ms",
        "tpot_p50_ms", "tpot_p99_ms",
        "e2el_p50_ms", "e2el_p99_ms",
        "prompt_len_p50", "prompt_len_p99",
        "gen_len_p50", "gen_len_p99",
        "running", "waiting", "swapped", "kv_cache_pct",
        "gpu_hourly_total_usd", "n_gpus",
        "model_id", "quantization",
        "reference_id", "reference_theta_max_tok_s", "reference_source",
    ]

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._file = open(self._path, "a", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=self.COLUMNS)
        if self._path.stat().st_size == 0:
            self._writer.writeheader()
            self._file.flush()

    def log(self, snap: CostSnapshot) -> None:
        row = snap.to_dict()
        row["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._writer.writerow({k: row.get(k) for k in self.COLUMNS})
        self._file.flush()

    def close(self) -> None:
        self._file.close()
