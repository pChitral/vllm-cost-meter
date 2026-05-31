import pytest
import importlib.resources
import yaml


REQUIRED_PROTOCOL_KEYS = {
    "input_tokens_mean", "output_tokens_mean", "input_distribution",
    "arrival_pattern", "burstiness", "prefix_caching",
    "chunked_prefill", "sla_bound", "source",
}


@pytest.fixture
def curves():
    pkg = importlib.resources.files("vllm_cost_meter") / "data" / "benchmark_curves.yaml"
    with pkg.open("r") as f:
        return yaml.safe_load(f)["curves"]


def test_every_curve_has_workload_protocol(curves):
    for curve in curves:
        assert "workload_protocol" in curve, f"{curve['id']} missing workload_protocol"
        missing = REQUIRED_PROTOCOL_KEYS - curve["workload_protocol"].keys()
        assert not missing, f"{curve['id']} missing keys: {missing}"


def test_catalog_includes_sglang_curves(curves):
    # 6 H100 SGLang (S1-S6) + 2 A100 SGLang (AS1 Llama, M2 Mixtral)
    sglang_ids = [c["id"] for c in curves if c.get("engine") == "sglang"]
    assert len(sglang_ids) == 8, f"expected 8 SGLang curves, got: {sglang_ids}"


def test_catalog_includes_all_20_paper_configs(curves):
    # H100: C1-C6 (vLLM) + S1-S6 (SGLang); A100: A1-A4 (vLLM) + AS1 (SGLang) + M1-M3 (Mixtral cross-hardware)
    sources = sorted(c["source"] for c in curves)
    assert sources == sorted([
        "paper-C1", "paper-C2", "paper-C3", "paper-C4", "paper-C5", "paper-C6",
        "paper-S1", "paper-S2", "paper-S3", "paper-S4", "paper-S5", "paper-S6",
        "paper-A1", "paper-A2", "paper-A3", "paper-A4",
        "paper-AS1",
        "paper-M1", "paper-M2", "paper-M3",
    ])


def test_catalog_includes_a100_cross_hardware_curves(curves):
    a100_ids = [c["id"] for c in curves if c.get("gpu_type") == "a100"]
    assert len(a100_ids) == 8, f"expected 8 A100 curves, got: {a100_ids}"
