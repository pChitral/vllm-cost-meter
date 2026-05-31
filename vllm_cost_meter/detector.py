# vllm_cost_meter/detector.py
"""
Detect running vLLM process configuration.

Priority order:
1. User-provided override (CLI flags --model, --quantization, --tensor-parallel-size)
2. /proc scan for vLLM process cmdline
3. GET /v1/models for model name (quantization unknown -> float16 default)
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional
import psutil
import requests


@dataclass
class VllmConfig:
    model_id: str
    quantization: str = "float16"  # float16 | fp8 | int8 | int4
    tensor_parallel_size: int = 1

    @property
    def n_gpus(self) -> int:
        return self.tensor_parallel_size

    def display_name(self) -> str:
        short = self.model_id.split("/")[-1]
        return f"{short} · {self.quantization} · {self.n_gpus}×GPU"


def parse_vllm_cmdline(cmdline: list[str]) -> VllmConfig:
    """Extract VllmConfig from a process cmdline list."""
    joined = " ".join(cmdline)

    # model: handle both --model <name> and `vllm serve <name>`
    m = re.search(r"(?:--model\s+|serve\s+)(\S+)", joined)
    model_id = m.group(1) if m else "unknown"

    # quantization: --quantization fp8 takes priority over --dtype float16
    quant = "float16"
    m = re.search(r"--quantization\s+(\S+)", joined)
    if m:
        quant = m.group(1)
    else:
        m = re.search(r"--dtype\s+(\S+)", joined)
        if m:
            quant = m.group(1)

    # tensor parallel size
    tp = 1
    m = re.search(r"--tensor-parallel-size\s+(\d+)", joined)
    if m:
        tp = int(m.group(1))

    return VllmConfig(model_id=model_id, quantization=quant, tensor_parallel_size=tp)


def _find_vllm_process() -> Optional[list[str]]:
    """Scan /proc for a running vLLM server process. Returns cmdline or None."""
    for proc in psutil.process_iter(["cmdline"]):
        try:
            cmdline = proc.info["cmdline"] or []
            joined = " ".join(cmdline)
            if "vllm" in joined and (
                "api_server" in joined or "serve" in joined
            ):
                return cmdline
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def _query_models_endpoint(base_url: str) -> Optional[str]:
    """GET /v1/models and return first model id, or None."""
    try:
        r = requests.get(f"{base_url}/v1/models", timeout=3)
        r.raise_for_status()
        data = r.json()
        models = data.get("data", [])
        if models:
            return models[0]["id"]
    except Exception:
        pass
    return None


def detect_vllm_config(
    override: Optional[VllmConfig] = None,
    base_url: str = "http://localhost:8000",
) -> VllmConfig:
    """
    Return VllmConfig by auto-detection or user override.

    Detection order:
    1. override (user-provided CLI flags) -> return immediately
    2. /proc scan for vLLM cmdline
    3. /v1/models endpoint for model name (quantization unknown, defaults float16)
    4. All unknown -> VllmConfig("unknown", "float16", 1)
    """
    if override is not None:
        return override

    cmdline = _find_vllm_process()
    if cmdline:
        config = parse_vllm_cmdline(cmdline)
        if config.model_id == "unknown":
            model_from_api = _query_models_endpoint(base_url)
            if model_from_api:
                config.model_id = model_from_api
        return config

    model_from_api = _query_models_endpoint(base_url)
    if model_from_api:
        return VllmConfig(model_id=model_from_api, quantization="float16", tensor_parallel_size=1)

    return VllmConfig(model_id="unknown", quantization="float16", tensor_parallel_size=1)
