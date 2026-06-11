# vllm_cost_meter/server.py
"""
Minimal HTTP server exposing /cost (JSON) and /metrics (Prometheus).
Runs in a daemon thread alongside the main scrape loop.
"""
from __future__ import annotations
import errno
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from vllm_cost_meter.cost import CostSnapshot


def _escape_label_value(value) -> str:
    """Escape a Prometheus label value per the exposition format: a backslash,
    double-quote, and line feed become ``\\\\``, ``\\"``, and ``\\n``.
    Backslash must be escaped first."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )


class MetricsServer:
    def __init__(self, port: int = 9090, host: str = "127.0.0.1"):
        self.port = port
        self.host = host
        self._snapshot: Optional[CostSnapshot] = None
        self._lock = threading.Lock()
        self._httpd: Optional[HTTPServer] = None

    def update(self, snapshot: CostSnapshot) -> None:
        with self._lock:
            self._snapshot = snapshot

    def _get_snapshot(self) -> Optional[CostSnapshot]:
        with self._lock:
            return self._snapshot

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # suppress access logs

            def do_GET(self):
                snap = server._get_snapshot()
                if self.path == "/cost":
                    self._serve_json(snap)
                elif self.path == "/metrics":
                    self._serve_prometheus(snap)
                else:
                    self.send_response(404)
                    self.end_headers()

            def _serve_json(self, snap):
                data = snap.to_dict() if snap else {}
                body = json.dumps(data, indent=2).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def _serve_prometheus(self, snap):
                lines = []
                if snap:
                    d = snap.to_dict()
                    labels = (
                        f'model="{_escape_label_value(snap.config.model_id)}",'
                        f'quant="{_escape_label_value(snap.config.quantization)}",'
                        f'n_gpus="{snap.n_gpus}"'
                    )

                    def gauge(name, help_text, value):
                        if value is None:
                            return
                        lines.append(f"# HELP {name} {help_text}")
                        lines.append(f"# TYPE {name} gauge")
                        lines.append(f"{name}{{{labels}}} {value}")

                    gauge("llm_cost_meter_eff_cost_per_mtok",
                          "Live effective cost per million output tokens USD",
                          d["eff_cost_per_mtok"])
                    gauge("llm_cost_meter_tps_observed",
                          "Rolling-window output tokens per second",
                          d["tps_out"])
                    gauge("llm_cost_meter_tps_input",
                          "Rolling-window input (prompt) tokens per second",
                          d["tps_in"])
                    gauge("llm_cost_meter_lambda_rps",
                          "Rolling-window request arrival rate",
                          d["lambda_rps"])
                    gauge("llm_cost_meter_ttft_p50_ms",
                          "Time-to-first-token p50 milliseconds", d["ttft_p50_ms"])
                    gauge("llm_cost_meter_ttft_p90_ms",
                          "Time-to-first-token p90 milliseconds", d["ttft_p90_ms"])
                    gauge("llm_cost_meter_ttft_p99_ms",
                          "Time-to-first-token p99 milliseconds", d["ttft_p99_ms"])
                    gauge("llm_cost_meter_tpot_p50_ms",
                          "Time-per-output-token p50 milliseconds", d["tpot_p50_ms"])
                    gauge("llm_cost_meter_tpot_p99_ms",
                          "Time-per-output-token p99 milliseconds", d["tpot_p99_ms"])
                    gauge("llm_cost_meter_e2el_p50_ms",
                          "End-to-end request latency p50 milliseconds", d["e2el_p50_ms"])
                    gauge("llm_cost_meter_e2el_p99_ms",
                          "End-to-end request latency p99 milliseconds", d["e2el_p99_ms"])
                    gauge("llm_cost_meter_prompt_len_p99",
                          "Prompt tokens per request p99", d["prompt_len_p99"])
                    gauge("llm_cost_meter_gen_len_p99",
                          "Generated tokens per request p99", d["gen_len_p99"])
                    gauge("llm_cost_meter_batch_running",
                          "Currently running requests on GPU", d["running"])
                    gauge("llm_cost_meter_batch_waiting",
                          "Currently queued requests", d["waiting"])
                    gauge("llm_cost_meter_batch_swapped",
                          "Requests swapped to CPU", d["swapped"])
                    gauge("llm_cost_meter_kv_cache_pct",
                          "GPU KV-cache utilization percent", d["kv_cache_pct"])

                body = "\n".join(lines).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4")
                self.end_headers()
                self.wfile.write(body)

        return Handler

    def _bind(self) -> None:
        """Create and bind the HTTP server. Idempotent."""
        if self._httpd is not None:
            return

        class _ReusableHTTPServer(HTTPServer):
            allow_reuse_address = True

        try:
            self._httpd = _ReusableHTTPServer((self.host, self.port), self._make_handler())
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                sys.exit(
                    f"Error: {self.host}:{self.port} is already in use — "
                    f"another meter or service is bound there. "
                    f"Pass --port N to pick a different port."
                )
            raise

    def serve_forever(self) -> None:
        self._bind()
        self._httpd.serve_forever()

    def shutdown(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    def start_background(self) -> threading.Thread:
        # Bind on the caller thread so the test/caller can read the bound
        # port via self._httpd.server_address before the daemon thread races.
        self._bind()
        t = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        t.start()
        return t
