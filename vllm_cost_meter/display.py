# vllm_cost_meter/display.py
"""
Objective terminal dashboard. Neutral, non-editorialised framing.
Shows: live C_eff, throughput, latency percentiles, batch state, KV cache,
optional SLO comparison, catalog reference context (when a match exists).
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from vllm_cost_meter.cost import CostSnapshot, api_crossover_summary

console = Console()


def _fmt_ms(v: Optional[float]) -> str:
    return f"{v:.0f}ms" if v is not None else "-"


def _fmt_num(v: Optional[float], suffix: str = "") -> str:
    return f"{v:.0f}{suffix}" if v is not None else "-"


def _fmt_money(v: Optional[float]) -> str:
    return f"${v:.3f}/MTok" if v is not None else "-"


def render(
    snap: CostSnapshot,
    *,
    slo_ttft_p99_ms: Optional[int] = None,
    slo_tpot_p99_ms: Optional[int] = None,
    slo_e2el_p99_ms: Optional[int] = None,
    show_api: bool = False,
) -> None:
    console.clear()
    t = snap.telemetry
    ts = datetime.now().strftime("%H:%M:%S")
    title = (f"vllm-cost-meter | {snap.config.display_name()} | "
             f"${snap.gpu_hourly_total:.2f}/hr | {ts}")

    tbl = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    tbl.add_column(style="bold dim", width=22)
    tbl.add_column()

    tbl.add_row("C_eff (live)", _fmt_money(snap.c_eff))
    tbl.add_row("Throughput out / in", f"{_fmt_num(t.tps_out, ' tok/s')}  /  {_fmt_num(t.tps_in, ' tok/s')}")
    tbl.add_row("Arrival rate lambda", _fmt_num(t.lambda_rps, " req/s"))
    tbl.add_row("Prompt len p50 / p99", f"{_fmt_num(t.prompt_len_p50)}  /  {_fmt_num(t.prompt_len_p99)}")
    tbl.add_row("Gen len p50 / p99", f"{_fmt_num(t.gen_len_p50)}  /  {_fmt_num(t.gen_len_p99)}")
    tbl.add_row("TTFT p50 / p90 / p99", f"{_fmt_ms(t.ttft_p50_ms)}  /  {_fmt_ms(t.ttft_p90_ms)}  /  {_fmt_ms(t.ttft_p99_ms)}")
    tbl.add_row("TPOT p50 / p99", f"{_fmt_ms(t.tpot_p50_ms)}  /  {_fmt_ms(t.tpot_p99_ms)}")
    tbl.add_row("E2E latency p50 / p99", f"{_fmt_ms(t.e2el_p50_ms)}  /  {_fmt_ms(t.e2el_p99_ms)}")
    tbl.add_row("Batch running / wait / swap",
                f"{_fmt_num(t.running)}  /  {_fmt_num(t.waiting)}  /  {_fmt_num(t.swapped)}")
    if t.kv_cache_pct is not None:
        tbl.add_row("KV cache usage", f"{t.kv_cache_pct*100:.0f}%")

    console.print(Panel(tbl, title=title, border_style="blue"))

    if snap.reference is not None:
        proto = snap.reference.protocol
        proto_line = (
            f"I/O {proto.get('input_tokens_mean', '?')}/"
            f"{proto.get('output_tokens_mean', '?')} {proto.get('input_distribution', '?')} | "
            f"{proto.get('arrival_pattern', '?')} | "
            f"prefix-cache {'on' if proto.get('prefix_caching') else 'off'} | "
            f"sla {proto.get('sla_bound') or 'none (raw saturation)'}"
        )
        ref_lines = [
            f"[bold]Reference ({snap.reference.source})[/bold]: "
            f"theta_max = {snap.reference.theta_max_tok_s:.0f} tok/s at peak concurrency",
            f"  Protocol: {proto_line}",
            f"  -> Load-test your own workload shape + SLO to get a ceiling for your deployment.",
        ]
        console.print(Panel("\n".join(ref_lines),
                            title="Catalog reference (neutral)", border_style="dim"))

    slo_parts = []
    if slo_ttft_p99_ms is not None:
        obs = t.ttft_p99_ms
        mark = "[OK]" if (obs is not None and obs <= slo_ttft_p99_ms) else "[FAIL]" if obs is not None else "-"
        slo_parts.append(f"TTFT p99 {_fmt_ms(obs)} / {slo_ttft_p99_ms}ms {mark}")
    if slo_tpot_p99_ms is not None:
        obs = t.tpot_p99_ms
        mark = "[OK]" if (obs is not None and obs <= slo_tpot_p99_ms) else "[FAIL]" if obs is not None else "-"
        slo_parts.append(f"TPOT p99 {_fmt_ms(obs)} / {slo_tpot_p99_ms}ms {mark}")
    if slo_e2el_p99_ms is not None:
        obs = t.e2el_p99_ms
        mark = "[OK]" if (obs is not None and obs <= slo_e2el_p99_ms) else "[FAIL]" if obs is not None else "-"
        slo_parts.append(f"E2EL p99 {_fmt_ms(obs)} / {slo_e2el_p99_ms}ms {mark}")
    if slo_parts:
        console.print(f"[bold]SLO status:[/bold] " + " | ".join(slo_parts))

    if show_api and snap.c_eff is not None:
        console.print(Panel(
            "[yellow]API pricing below is serverless (no SLO). Your dedicated "
            "deployment's C_eff is your real cost only if your SLO is met. "
            "Review the paper's 'Serverless-vs-Dedicated Fallacy' subsection "
            "before using these numbers in a buy-vs-build decision.[/yellow]",
            border_style="yellow"))
        comparisons = api_crossover_summary(snap.c_eff)[:6]
        api_table = Table(title="API comparison (not apples-to-apples - see banner above)",
                          box=box.SIMPLE, show_header=True, header_style="bold")
        api_table.add_column("Provider")
        api_table.add_column("Model")
        api_table.add_column("Blended $/MTok", justify="right")
        for c in comparisons:
            api_table.add_row(c["provider"], c["api_id"],
                              f"${c['blended_per_mtok']:.3f}")
        console.print(api_table)
