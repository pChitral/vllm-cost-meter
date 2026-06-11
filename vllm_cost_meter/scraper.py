# vllm_cost_meter/scraper.py
"""
Scrape vLLM Prometheus /metrics and compute rolling-window TPS + percentile rollups.

Parses counters, gauges, and histograms from the Prometheus text format
exposed by vLLM (validated against 0.19.x; SGLang 0.5.x exposes a compatible
field schema). Percentile readout uses Prometheus's conservative upper-bound
bucket lookup — i.e. the upper edge of the first cumulative bucket whose
count meets the target — without linear interpolation.
"""
from __future__ import annotations
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
import requests


def _counter_re(name: str) -> re.Pattern:
    return re.compile(rf"^{re.escape(name)}\{{[^}}]*\}}\s+([\d.eE+-]+)", re.MULTILINE)


_GEN_TOKENS_RE = _counter_re("vllm:generation_tokens_total")
_PROMPT_TOKENS_RE = _counter_re("vllm:prompt_tokens_total")
_REQUESTS_TOTAL_RE = _counter_re("vllm:request_success_total")


def parse_generation_tokens(text: str) -> Optional[float]:
    m = _GEN_TOKENS_RE.search(text)
    return float(m.group(1)) if m else None


def parse_prompt_tokens(text: str) -> Optional[float]:
    m = _PROMPT_TOKENS_RE.search(text)
    return float(m.group(1)) if m else None


def parse_requests_total(text: str) -> Optional[float]:
    m = _REQUESTS_TOTAL_RE.search(text)
    return float(m.group(1)) if m else None


def parse_gauge(text: str, name: str) -> Optional[float]:
    m = _counter_re(name).search(text)
    return float(m.group(1)) if m else None


_BUCKET_RE_TEMPLATE = r'^{name}_bucket\{{[^}}]*le="([^"]+)"[^}}]*\}}\s+([\d.eE+-]+)'


def parse_histogram_count(text: str, name: str) -> Optional[float]:
    pat = re.compile(rf"^{re.escape(name)}_count\{{[^}}]*\}}\s+([\d.eE+-]+)", re.MULTILINE)
    m = pat.search(text)
    return float(m.group(1)) if m else None


def parse_histogram_percentile(text: str, name: str, percentile: float) -> Optional[float]:
    """
    Compute bucket percentile from Prometheus cumulative histogram.

    Returns the upper bound of the first cumulative bucket whose count
    meets or exceeds `percentile * total`. This matches Prometheus's
    conservative (upper-bound) reporting for histogram_quantile when the
    underlying distribution lacks finer-grained buckets. Value is in the
    same unit as the histogram.
    """
    pat = re.compile(_BUCKET_RE_TEMPLATE.format(name=re.escape(name)), re.MULTILINE)
    buckets: list[tuple[float, float]] = []
    for le_str, count_str in pat.findall(text):
        le = float("inf") if le_str == "+Inf" else float(le_str)
        buckets.append((le, float(count_str)))
    if not buckets:
        return None
    buckets.sort(key=lambda x: x[0])
    total = buckets[-1][1]
    if total <= 0:
        return None
    target = percentile * total
    prev_le = 0.0
    for le, count in buckets:
        if count >= target:
            if le == float("inf"):
                return prev_le
            return le
        prev_le = le
    return buckets[-1][0]


@dataclass
class LiveTelemetry:
    """Everything pulled from a single /metrics scrape plus rolling rates."""
    tps_out: Optional[float] = None             # output tok/s (rolling)
    tps_in: Optional[float] = None              # input tok/s (rolling)
    lambda_rps: Optional[float] = None          # requests/s (rolling)
    ttft_p50_ms: Optional[float] = None
    ttft_p90_ms: Optional[float] = None
    ttft_p99_ms: Optional[float] = None
    tpot_p50_ms: Optional[float] = None
    tpot_p99_ms: Optional[float] = None
    e2el_p50_ms: Optional[float] = None
    e2el_p99_ms: Optional[float] = None
    prompt_len_p50: Optional[float] = None
    prompt_len_p99: Optional[float] = None
    gen_len_p50: Optional[float] = None
    gen_len_p99: Optional[float] = None
    running: Optional[float] = None
    waiting: Optional[float] = None
    swapped: Optional[float] = None
    kv_cache_pct: Optional[float] = None
    scraped_at: float = field(default_factory=time.monotonic)


class MetricsScraper:
    """Rolling-window scraper. Maintains deques for counters to derive rates."""

    def __init__(self, base_url: str, window_seconds: int = 300):
        self.base_url = base_url.rstrip("/")
        self.window_seconds = window_seconds
        self._gen_samples: deque[tuple[float, float]] = deque()
        self._prompt_samples: deque[tuple[float, float]] = deque()
        self._req_samples: deque[tuple[float, float]] = deque()

    def _append(self, dq: deque, value: Optional[float], t: float) -> None:
        if value is None:
            return
        dq.append((value, t))
        cutoff = t - self.window_seconds
        while dq and dq[0][1] < cutoff:
            dq.popleft()

    @staticmethod
    def _rate(dq: deque) -> Optional[float]:
        if len(dq) < 2:
            return None
        v0, t0 = dq[0]
        v1, t1 = dq[-1]
        dt = t1 - t0
        if dt <= 0:
            return None
        if v1 < v0:
            # counter reset (e.g. server restart): rate is meaningless until the
            # pre-reset sample ages out of the rolling window
            return None
        return (v1 - v0) / dt

    def scrape(self) -> LiveTelemetry:
        r = requests.get(f"{self.base_url}/metrics", timeout=5)
        r.raise_for_status()
        text = r.text
        now = time.monotonic()

        self._append(self._gen_samples, parse_generation_tokens(text), now)
        self._append(self._prompt_samples, parse_prompt_tokens(text), now)
        self._append(self._req_samples, parse_requests_total(text), now)

        def ms(v: Optional[float]) -> Optional[float]:
            return v * 1000.0 if v is not None else None

        return LiveTelemetry(
            tps_out=self._rate(self._gen_samples),
            tps_in=self._rate(self._prompt_samples),
            lambda_rps=self._rate(self._req_samples),
            ttft_p50_ms=ms(parse_histogram_percentile(text, "vllm:time_to_first_token_seconds", 0.50)),
            ttft_p90_ms=ms(parse_histogram_percentile(text, "vllm:time_to_first_token_seconds", 0.90)),
            ttft_p99_ms=ms(parse_histogram_percentile(text, "vllm:time_to_first_token_seconds", 0.99)),
            tpot_p50_ms=ms(parse_histogram_percentile(text, "vllm:time_per_output_token_seconds", 0.50)),
            tpot_p99_ms=ms(parse_histogram_percentile(text, "vllm:time_per_output_token_seconds", 0.99)),
            e2el_p50_ms=ms(parse_histogram_percentile(text, "vllm:e2e_request_latency_seconds", 0.50)),
            e2el_p99_ms=ms(parse_histogram_percentile(text, "vllm:e2e_request_latency_seconds", 0.99)),
            prompt_len_p50=parse_histogram_percentile(text, "vllm:request_prompt_tokens", 0.50),
            prompt_len_p99=parse_histogram_percentile(text, "vllm:request_prompt_tokens", 0.99),
            gen_len_p50=parse_histogram_percentile(text, "vllm:request_generation_tokens", 0.50),
            gen_len_p99=parse_histogram_percentile(text, "vllm:request_generation_tokens", 0.99),
            running=parse_gauge(text, "vllm:num_requests_running"),
            waiting=parse_gauge(text, "vllm:num_requests_waiting"),
            swapped=parse_gauge(text, "vllm:num_requests_swapped"),
            kv_cache_pct=parse_gauge(text, "vllm:gpu_cache_usage_perc"),
            scraped_at=now,
        )
