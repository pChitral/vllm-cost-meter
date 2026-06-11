# tests/test_detector.py
import pytest
from unittest.mock import patch, MagicMock
from vllm_cost_meter.detector import VllmConfig, detect_vllm_config, parse_vllm_cmdline


def test_parse_cmdline_quantization_fp8():
    cmdline = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", "meta-llama/Meta-Llama-3.1-8B-Instruct",
        "--quantization", "fp8",
        "--tensor-parallel-size", "2",
    ]
    config = parse_vllm_cmdline(cmdline)
    assert config.quantization == "fp8"
    assert config.tensor_parallel_size == 2
    assert "Llama-3.1-8B" in config.model_id


def test_parse_cmdline_dtype_float16():
    cmdline = [
        "vllm", "serve", "meta-llama/Meta-Llama-3.1-8B-Instruct",
        "--dtype", "float16",
    ]
    config = parse_vllm_cmdline(cmdline)
    assert config.quantization == "float16"
    assert config.tensor_parallel_size == 1  # default


def test_parse_cmdline_no_quant_defaults_to_float16():
    cmdline = ["python", "-m", "vllm.entrypoints.openai.api_server",
               "--model", "some-model"]
    config = parse_vllm_cmdline(cmdline)
    assert config.quantization == "float16"


def test_vllm_config_n_gpus():
    config = VllmConfig(model_id="llama", quantization="fp8", tensor_parallel_size=2)
    assert config.n_gpus == 2


def test_detect_returns_override_when_provided():
    override = VllmConfig(model_id="my-model", quantization="fp8", tensor_parallel_size=1)
    result = detect_vllm_config(override=override)
    assert result == override
