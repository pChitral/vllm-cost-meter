# tests/test_server.py
import json
import threading
import time
import requests
import pytest
from vllm_cost_meter.cost import CostEngine
from vllm_cost_meter.detector import VllmConfig
from vllm_cost_meter.scraper import LiveTelemetry
from vllm_cost_meter.server import MetricsServer


@pytest.fixture
def server_with_snapshot():
    srv = MetricsServer(port=0)  # ephemeral
    engine = CostEngine(gpu_hourly_cost=6.98, n_gpus=1)
    config = VllmConfig(model_id="meta-llama/Meta-Llama-3.1-8B-Instruct",
                        quantization="fp8", tensor_parallel_size=1)
    snap = engine.snapshot(
        telemetry=LiveTelemetry(
            tps_out=1842.0, tps_in=3684.0, lambda_rps=4.1,
            ttft_p99_ms=280.0, tpot_p99_ms=42.0, e2el_p99_ms=3800.0,
            prompt_len_p99=1024, gen_len_p99=512,
            running=6, waiting=0, swapped=0, kv_cache_pct=0.38,
        ),
        config=config,
    )
    srv.update(snap)
    srv.start_background()
    time.sleep(0.2)
    yield srv
    srv.shutdown()


def test_prometheus_includes_new_gauges(server_with_snapshot):
    port = server_with_snapshot._httpd.server_address[1]
    r = requests.get(f"http://localhost:{port}/metrics", timeout=5)
    text = r.text
    expected = [
        "llm_cost_meter_eff_cost_per_mtok",
        "llm_cost_meter_tps_observed",
        "llm_cost_meter_tps_input",
        "llm_cost_meter_lambda_rps",
        "llm_cost_meter_ttft_p99_ms",
        "llm_cost_meter_tpot_p99_ms",
        "llm_cost_meter_e2el_p99_ms",
        "llm_cost_meter_batch_running",
        "llm_cost_meter_kv_cache_pct",
    ]
    for name in expected:
        assert name in text, f"missing gauge: {name}"


def test_prometheus_excludes_judgement_gauges(server_with_snapshot):
    port = server_with_snapshot._httpd.server_address[1]
    r = requests.get(f"http://localhost:{port}/metrics", timeout=5)
    text = r.text
    for forbidden in ("saturation_cost_per_mtok", "utilization_pct", "penalty_multiplier"):
        assert forbidden not in text, f"judgement gauge leaked: {forbidden}"


def test_cost_json_schema(server_with_snapshot):
    port = server_with_snapshot._httpd.server_address[1]
    r = requests.get(f"http://localhost:{port}/cost", timeout=5)
    d = r.json()
    assert "eff_cost_per_mtok" in d
    assert "ttft_p99_ms" in d
    assert "reference_theta_max_tok_s" in d
    assert "penalty_multiplier" not in d
