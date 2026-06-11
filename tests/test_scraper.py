# tests/test_scraper.py
from pathlib import Path
import pytest
from collections import deque
from vllm_cost_meter.scraper import (
    parse_generation_tokens, parse_prompt_tokens, parse_requests_total,
    parse_gauge, parse_histogram_percentile, parse_histogram_count,
    MetricsScraper,
)


FIXTURE = Path(__file__).parent / "fixtures" / "vllm_metrics_full.txt"


def _fixture_text():
    return FIXTURE.read_text()


SAMPLE_METRICS = """
# HELP vllm:generation_tokens_total Number of generation tokens processed.
# TYPE vllm:generation_tokens_total counter
vllm:generation_tokens_total{model_name="meta-llama/Meta-Llama-3.1-8B-Instruct",engine_version="vllm"} 1500000.0
# HELP vllm:num_requests_running Number of requests currently running.
vllm:num_requests_running{model_name="meta-llama/Meta-Llama-3.1-8B-Instruct"} 12.0
"""


def test_parse_generation_tokens():
    assert parse_generation_tokens(SAMPLE_METRICS) == 1_500_000.0


def test_parse_generation_tokens_missing_returns_none():
    assert parse_generation_tokens("# no relevant metrics here") is None


def test_parse_prompt_tokens():
    assert parse_prompt_tokens(_fixture_text()) == 2345678.0


def test_parse_requests_total():
    assert parse_requests_total(_fixture_text()) == 4567.0


def test_parse_gauge_running():
    assert parse_gauge(_fixture_text(), "vllm:num_requests_running") == 6.0


def test_parse_gauge_waiting():
    assert parse_gauge(_fixture_text(), "vllm:num_requests_waiting") == 2.0


def test_parse_gauge_kv_cache():
    assert parse_gauge(_fixture_text(), "vllm:gpu_cache_usage_perc") == 0.38


def test_parse_histogram_count():
    assert parse_histogram_count(_fixture_text(),
                                 "vllm:time_to_first_token_seconds") == 4567.0


def test_parse_histogram_p99_ttft_approx():
    # Bucket le=0.5 has 4560, le=1.0 has 4567, count=4567 -> p99 ~ 0.5s boundary
    p99 = parse_histogram_percentile(
        _fixture_text(), "vllm:time_to_first_token_seconds", percentile=0.99
    )
    assert p99 is not None
    assert 0.3 <= p99 <= 1.0


def test_parse_histogram_p50_ttft_approx():
    p50 = parse_histogram_percentile(
        _fixture_text(), "vllm:time_to_first_token_seconds", percentile=0.50
    )
    assert p50 is not None
    assert 0.01 <= p50 <= 0.1


def test_rate_normal_positive():
    dq = deque([(1000.0, 10.0), (2000.0, 20.0)])
    assert MetricsScraper._rate(dq) == 100.0


def test_rate_counter_reset_returns_none():
    # v1 < v0 means the counter reset (e.g. server restart); the two-point rate
    # would be negative, so it must be suppressed.
    dq = deque([(5000.0, 10.0), (200.0, 20.0)])
    assert MetricsScraper._rate(dq) is None


def test_rate_insufficient_samples_returns_none():
    assert MetricsScraper._rate(deque([(1.0, 1.0)])) is None
