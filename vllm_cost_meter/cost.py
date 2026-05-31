# vllm_cost_meter/cost.py
"""
Core cost computations - objective, no judgement fields.

C_eff = gpu_hourly_total / (tps_out * 3600 / 1_000_000)

Catalog reference lookup returns raw-saturation theta_max with its declared
workload protocol. Consumers display it as neutral context only - no
editorialised derivations.
"""
from __future__ import annotations
import importlib.resources
from dataclasses import dataclass, field
from typing import Optional
import yaml

from vllm_cost_meter.detector import VllmConfig
from vllm_cost_meter.scraper import LiveTelemetry


def _load_curves() -> list[dict]:
    pkg = importlib.resources.files("vllm_cost_meter") / "data" / "benchmark_curves.yaml"
    with pkg.open("r") as f:
        data = yaml.safe_load(f)
    return data.get("curves", [])


def _load_api_pricing() -> dict:
    pkg = importlib.resources.files("vllm_cost_meter") / "data" / "api_pricing.yaml"
    with pkg.open("r") as f:
        data = yaml.safe_load(f)
    return data.get("api_pricing", {})


_CURVES: list[dict] = _load_curves()
_API_PRICING: dict = _load_api_pricing()


def compute_c_eff(gpu_hourly_total: float, tps: Optional[float]) -> Optional[float]:
    """C_eff in $/MTok. Returns None if tps is None or zero."""
    if not tps:
        return None
    return gpu_hourly_total / (tps * 3600.0 / 1_000_000.0)


def find_curve(config: VllmConfig) -> Optional[dict]:
    model_lower = config.model_id.lower()
    quant_lower = config.quantization.lower()
    for curve in _CURVES:
        if curve["n_gpus"] != config.n_gpus:
            continue
        if curve["quantization"].lower() != quant_lower:
            continue
        all_names = [curve["model_id"]] + curve.get("model_aliases", [])
        if any(name.lower() in model_lower or model_lower in name.lower()
               for name in all_names):
            return curve
    return None


def api_crossover_summary(c_eff: float, input_tokens: int = 512,
                           output_tokens: int = 256) -> list[dict]:
    results = []
    total = input_tokens + output_tokens
    for api_id, info in _API_PRICING.items():
        blended = (info["input_per_mtok"] * input_tokens +
                   info["output_per_mtok"] * output_tokens) / total
        results.append({
            "api_id": api_id,
            "provider": info["provider"],
            "blended_per_mtok": blended,
            "cheaper_than_self_hosted": blended < c_eff,
        })
    return sorted(results, key=lambda x: x["blended_per_mtok"])


@dataclass
class CatalogReference:
    """Neutral reference data from the benchmark catalog. No derived judgements."""
    id: str
    source: str  # e.g. "paper-C2"
    engine: str
    theta_max_tok_s: float
    protocol: dict  # workload_protocol block as dict

    @classmethod
    def from_curve(cls, curve: dict) -> "CatalogReference":
        return cls(
            id=curve["id"],
            source=curve["source"],
            engine=curve.get("engine", "unknown"),
            theta_max_tok_s=float(curve["theta_max_tok_s"]),
            protocol=dict(curve.get("workload_protocol", {})),
        )


@dataclass
class CostSnapshot:
    c_eff: Optional[float]
    telemetry: LiveTelemetry
    config: VllmConfig
    gpu_hourly_total: float
    n_gpus: int
    reference: Optional[CatalogReference] = None

    def to_dict(self) -> dict:
        t = self.telemetry
        return {
            "eff_cost_per_mtok": round(self.c_eff, 4) if self.c_eff is not None else None,
            "tps_out": round(t.tps_out, 1) if t.tps_out is not None else None,
            "tps_in": round(t.tps_in, 1) if t.tps_in is not None else None,
            "lambda_rps": round(t.lambda_rps, 2) if t.lambda_rps is not None else None,
            "ttft_p50_ms": round(t.ttft_p50_ms, 1) if t.ttft_p50_ms is not None else None,
            "ttft_p90_ms": round(t.ttft_p90_ms, 1) if t.ttft_p90_ms is not None else None,
            "ttft_p99_ms": round(t.ttft_p99_ms, 1) if t.ttft_p99_ms is not None else None,
            "tpot_p50_ms": round(t.tpot_p50_ms, 1) if t.tpot_p50_ms is not None else None,
            "tpot_p99_ms": round(t.tpot_p99_ms, 1) if t.tpot_p99_ms is not None else None,
            "e2el_p50_ms": round(t.e2el_p50_ms, 1) if t.e2el_p50_ms is not None else None,
            "e2el_p99_ms": round(t.e2el_p99_ms, 1) if t.e2el_p99_ms is not None else None,
            "prompt_len_p50": round(t.prompt_len_p50, 0) if t.prompt_len_p50 is not None else None,
            "prompt_len_p99": round(t.prompt_len_p99, 0) if t.prompt_len_p99 is not None else None,
            "gen_len_p50": round(t.gen_len_p50, 0) if t.gen_len_p50 is not None else None,
            "gen_len_p99": round(t.gen_len_p99, 0) if t.gen_len_p99 is not None else None,
            "running": int(t.running) if t.running is not None else None,
            "waiting": int(t.waiting) if t.waiting is not None else None,
            "swapped": int(t.swapped) if t.swapped is not None else None,
            "kv_cache_pct": round(t.kv_cache_pct * 100, 1) if t.kv_cache_pct is not None else None,
            "gpu_hourly_total_usd": self.gpu_hourly_total,
            "n_gpus": self.n_gpus,
            "model_id": self.config.model_id,
            "quantization": self.config.quantization,
            "reference_id": self.reference.id if self.reference else None,
            "reference_theta_max_tok_s": self.reference.theta_max_tok_s if self.reference else None,
            "reference_source": self.reference.source if self.reference else None,
        }


class CostEngine:
    def __init__(self, gpu_hourly_cost: float, n_gpus: int = 1):
        self.gpu_hourly_cost = gpu_hourly_cost
        self.n_gpus = n_gpus
        self.gpu_hourly_total = gpu_hourly_cost * n_gpus

    def snapshot(self, telemetry: LiveTelemetry, config: VllmConfig) -> CostSnapshot:
        c_eff = compute_c_eff(self.gpu_hourly_total, telemetry.tps_out)
        curve = find_curve(config)
        reference = CatalogReference.from_curve(curve) if curve else None
        return CostSnapshot(
            c_eff=c_eff,
            telemetry=telemetry,
            config=config,
            gpu_hourly_total=self.gpu_hourly_total,
            n_gpus=self.n_gpus,
            reference=reference,
        )
