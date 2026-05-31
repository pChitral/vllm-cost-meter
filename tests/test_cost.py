# tests/test_cost.py
import pytest
from vllm_cost_meter.cost import (
    CostEngine, CostSnapshot, CatalogReference,
    compute_c_eff, find_curve, api_crossover_summary,
)
from vllm_cost_meter.detector import VllmConfig
from vllm_cost_meter.scraper import LiveTelemetry


def test_compute_c_eff_basic():
    c = compute_c_eff(gpu_hourly_total=6.98, tps=6238.0)
    assert abs(c - 0.311) < 0.005


def test_compute_c_eff_zero_tps_returns_none():
    assert compute_c_eff(gpu_hourly_total=6.98, tps=0.0) is None
    assert compute_c_eff(gpu_hourly_total=6.98, tps=None) is None


def test_snapshot_has_no_judgement_fields():
    # Snapshot must not expose waste/penalty/saturation - those are judgements.
    engine = CostEngine(gpu_hourly_cost=6.98, n_gpus=1)
    config = VllmConfig(model_id="llama-3.1-8b", quantization="fp8", tensor_parallel_size=1)
    telem = LiveTelemetry(tps_out=1842.0)
    snap = engine.snapshot(telemetry=telem, config=config)
    d = snap.to_dict()
    for forbidden in ("penalty_multiplier", "saturation_cost_per_mtok", "utilization_pct"):
        assert forbidden not in d, f"{forbidden} leaked into snapshot dict"


def test_snapshot_has_c_eff_from_live_tps():
    engine = CostEngine(gpu_hourly_cost=6.98, n_gpus=1)
    config = VllmConfig(model_id="llama-3.1-8b", quantization="fp8", tensor_parallel_size=1)
    telem = LiveTelemetry(tps_out=8155.0)
    snap = engine.snapshot(telemetry=telem, config=config)
    assert snap.c_eff is not None
    assert abs(snap.c_eff - 0.238) < 0.005


def test_snapshot_includes_catalog_reference_when_match():
    engine = CostEngine(gpu_hourly_cost=6.98, n_gpus=1)
    config = VllmConfig(model_id="meta-llama/Meta-Llama-3.1-8B-Instruct",
                        quantization="fp8", tensor_parallel_size=1)
    snap = engine.snapshot(telemetry=LiveTelemetry(tps_out=1000.0), config=config)
    assert snap.reference is not None
    assert snap.reference.theta_max_tok_s > 8000  # C2
    assert snap.reference.protocol["prefix_caching"] is False
    assert snap.reference.source == "paper-C2"


def test_snapshot_reference_is_none_when_no_catalog_match():
    engine = CostEngine(gpu_hourly_cost=6.98, n_gpus=1)
    config = VllmConfig(model_id="nonexistent-model", quantization="fp8", tensor_parallel_size=1)
    snap = engine.snapshot(telemetry=LiveTelemetry(tps_out=1000.0), config=config)
    assert snap.reference is None


def test_api_crossover_function_still_exists():
    # Keep the math; gating is in __main__.
    results = api_crossover_summary(c_eff=2.0)
    assert len(results) > 0
    assert all("blended_per_mtok" in r for r in results)
