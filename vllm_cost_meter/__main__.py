# vllm_cost_meter/__main__.py
"""
vllm-cost-meter CLI entry point (objective v1).

Examples:
  vllm-cost-meter --gpu-hourly-cost 6.98
  vllm-cost-meter --gpu-hourly-cost 6.98 --slo-ttft-p99-ms 300 --slo-tpot-p99-ms 50
  vllm-cost-meter --gpu-hourly-cost 6.98 --compare-api --accept-slo-mismatch
"""
from __future__ import annotations
import argparse
import math
import os
import signal
import sys
import time

from vllm_cost_meter import __version__
from vllm_cost_meter.cost import CostEngine
from vllm_cost_meter.detector import detect_vllm_config
from vllm_cost_meter.display import console, render
from vllm_cost_meter.logger import CsvLogger
from vllm_cost_meter.scraper import MetricsScraper
from vllm_cost_meter.server import MetricsServer


SLO_MISMATCH_BANNER = (
    "Refusing --compare-api without --accept-slo-mismatch.\n"
    "Serverless APIs publish no production TTFT/TPOT SLO. A dedicated self-hosted\n"
    "deployment with a real SLO is not comparable per-token. See the paper's\n"
    "'Serverless-vs-Dedicated Fallacy' subsection before relying on these numbers."
)


def _positive_float(raw: str) -> float:
    try:
        v = float(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a number, got {raw!r}")
    if not math.isfinite(v) or v <= 0:
        raise argparse.ArgumentTypeError(f"expected a positive finite number, got {v}")
    return v


def _positive_int(raw: str) -> int:
    try:
        v = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got {raw!r}")
    if v < 1:
        raise argparse.ArgumentTypeError(f"expected an integer >= 1, got {v}")
    return v


def _port(raw: str) -> int:
    try:
        v = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer port, got {raw!r}")
    if not 1 <= v <= 65535:
        raise argparse.ArgumentTypeError(f"port must be in [1, 65535], got {v}")
    return v


def _gpu_hourly_default() -> float | None:
    raw = os.environ.get("GPU_HOURLY_COST")
    if raw is None or raw == "":
        return None
    try:
        v = float(raw)
    except ValueError:
        console.print(
            f"[red]Error:[/red] GPU_HOURLY_COST env var is not a number: {raw!r}"
        )
        sys.exit(1)
    if not math.isfinite(v) or v <= 0:
        console.print(
            f"[red]Error:[/red] GPU_HOURLY_COST must be a positive finite number, got {v}"
        )
        sys.exit(1)
    return v


def main():
    parser = argparse.ArgumentParser(
        prog="vllm-cost-meter",
        description="Objective live telemetry + cost meter for vLLM inference servers.",
    )
    parser.add_argument("--version", action="version",
                        version=f"vllm-cost-meter {__version__}")
    parser.add_argument("--vllm-url", default="http://localhost:8000",
                        help="Base URL of the vLLM server (default: http://localhost:8000)")
    parser.add_argument("--gpu-hourly-cost", type=_positive_float,
                        default=_gpu_hourly_default(),
                        help="Per-GPU on-demand hourly USD rate (or set GPU_HOURLY_COST env)")
    parser.add_argument("--n-gpus", type=_positive_int, default=None,
                        help="Override detected GPU count for billing (default: detect from vLLM cmdline)")
    parser.add_argument("--window", type=_positive_int, default=5,
                        help="Rolling window size in minutes for TPS / lambda averaging (default: 5)")
    parser.add_argument("--bind", default="127.0.0.1",
                        help="Address to bind the meter HTTP server (default: 127.0.0.1; use 0.0.0.0 to expose externally)")
    parser.add_argument("--port", type=_port, default=9090,
                        help="Port for /cost (JSON) and /metrics (Prometheus) (default: 9090)")
    parser.add_argument("--compare-api", action="store_true",
                        help="Show serverless-API comparison (requires --accept-slo-mismatch)")
    parser.add_argument("--accept-slo-mismatch", action="store_true",
                        help="Acknowledge that serverless APIs have no SLO - required for --compare-api")
    parser.add_argument("--model", default=None,
                        help="Override detected model id (e.g. meta-llama/Meta-Llama-3.1-8B-Instruct)")
    parser.add_argument("--quantization", default=None,
                        help="Override detected quantization (float16 | fp8 | int8 | int4)")
    parser.add_argument("--tensor-parallel-size", type=_positive_int, default=None,
                        help="Override detected tensor-parallel size")
    parser.add_argument("--log-csv", default=None, metavar="PATH",
                        help="Append every snapshot to this CSV file (creates header on first row)")
    parser.add_argument("--slo-ttft-p99-ms", type=_positive_int, default=None,
                        help="Declared TTFT p99 budget in ms; meter shows observed vs budget")
    parser.add_argument("--slo-tpot-p99-ms", type=_positive_int, default=None,
                        help="Declared TPOT p99 budget in ms")
    parser.add_argument("--slo-e2el-p99-ms", type=_positive_int, default=None,
                        help="Declared end-to-end latency p99 budget in ms")

    args = parser.parse_args()

    if args.gpu_hourly_cost is None:
        console.print("[red]Error:[/red] --gpu-hourly-cost is required (or set GPU_HOURLY_COST env)")
        sys.exit(1)

    if args.compare_api and not args.accept_slo_mismatch:
        console.print(f"[red]{SLO_MISMATCH_BANNER}[/red]")
        sys.exit(2)

    if args.quantization is not None and args.quantization not in {"float16", "fp8", "int8", "int4"}:
        console.print(
            f"[red]Error:[/red] --quantization must be one of float16 | fp8 | int8 | int4, "
            f"got {args.quantization!r}"
        )
        sys.exit(1)

    # Auto-detect first, then overlay any explicitly-provided CLI flags so a
    # partial override (e.g. only --tensor-parallel-size) does not wipe the
    # other auto-detected fields.
    config = detect_vllm_config(base_url=args.vllm_url)
    if args.model:
        config.model_id = args.model
    if args.quantization:
        config.quantization = args.quantization
    if args.tensor_parallel_size:
        config.tensor_parallel_size = args.tensor_parallel_size
    n_gpus = args.n_gpus or config.n_gpus

    console.print(f"[bold]vllm-cost-meter {__version__}[/bold] starting...")
    console.print(f"  vLLM URL:  {args.vllm_url}")
    console.print(f"  Config:    {config.display_name()}")
    console.print(f"  GPU cost:  ${args.gpu_hourly_cost:.2f}/hr x {n_gpus} GPU = "
                  f"${args.gpu_hourly_cost * n_gpus:.2f}/hr total")
    console.print(f"  Window:    {args.window}m rolling")
    console.print(f"  Metrics:   http://{args.bind}:{args.port}/metrics")
    console.print(f"  REST:      http://{args.bind}:{args.port}/cost")
    if args.bind == "0.0.0.0":
        console.print("  [yellow]Note:[/yellow] bound to 0.0.0.0 — meter is reachable from any host on this network.")
    if args.slo_ttft_p99_ms or args.slo_tpot_p99_ms or args.slo_e2el_p99_ms:
        console.print(f"  SLO:       ttft={args.slo_ttft_p99_ms or '-'}ms "
                      f"tpot={args.slo_tpot_p99_ms or '-'}ms "
                      f"e2el={args.slo_e2el_p99_ms or '-'}ms")
    else:
        console.print("  [dim]SLO:       not declared - pass --slo-ttft-p99-ms N to see budget check[/dim]")

    scraper = MetricsScraper(base_url=args.vllm_url, window_seconds=args.window * 60)
    engine = CostEngine(gpu_hourly_cost=args.gpu_hourly_cost, n_gpus=n_gpus)
    server = MetricsServer(port=args.port, host=args.bind)
    server.start_background()

    csv_logger = CsvLogger(args.log_csv) if args.log_csv else None

    interval = max(min(args.window * 60 / 10, 30), 1)
    console.print(f"\n[dim]Scraping every {interval:.0f}s... (Ctrl+C to stop)[/dim]\n")

    stop = {"requested": False}

    def _request_stop(*_):
        stop["requested"] = True
    signal.signal(signal.SIGTERM, _request_stop)

    try:
        while not stop["requested"]:
            try:
                telem = scraper.scrape()
                snap = engine.snapshot(telemetry=telem, config=config)
                server.update(snap)
                render(
                    snap,
                    slo_ttft_p99_ms=args.slo_ttft_p99_ms,
                    slo_tpot_p99_ms=args.slo_tpot_p99_ms,
                    slo_e2el_p99_ms=args.slo_e2el_p99_ms,
                    show_api=args.compare_api,
                )
                if csv_logger:
                    csv_logger.log(snap)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                console.print(f"[yellow]Scrape error:[/yellow] {e} - retrying in {interval:.0f}s")
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
    finally:
        if csv_logger:
            csv_logger.close()
        server.shutdown()


if __name__ == "__main__":
    main()
