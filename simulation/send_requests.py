#!/usr/bin/env python3
"""
Enterprise load simulation for vllm-cost-meter demo.

Sends requests to a local vLLM server at ramping rates to demonstrate
how effective cost-per-million-tokens changes with GPU utilization.

Each phase sends requests at a fixed rate for --phase-duration seconds.
Run this alongside `vllm-cost-meter` to watch the dashboard update live.

Usage (on VM with vLLM running on localhost:8000):
  python simulation/send_requests.py
  python simulation/send_requests.py --base-url http://localhost:8000 --phase-duration 45
"""
import argparse
import time
import threading
import sys
from datetime import datetime

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)


# Simulation phases: (name, rps, default_duration_sec, description)
PHASES = [
    ("IDLE",       1,   60, "1 rps  — idle GPU, meter running, high C_eff"),
    ("TRICKLE",    5,   90, "5 rps  — low traffic, C_eff ~5x above naive baseline"),
    ("MODERATE",  10,   90, "10 rps — still underutilized, C_eff ~2.5x baseline"),
    ("GOOD",      25,   90, "25 rps — approaching crossover threshold"),
    ("SATURATED", 50,  120, "50 rps — near GPU saturation, minimum cost"),
    ("COOLDOWN",   1,   60, "1 rps  — back to idle, watch cost climb again"),
]

PROMPT = "Explain in one sentence what machine learning is."


def send_request(base_url: str, model: str) -> bool:
    try:
        r = requests.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": PROMPT}],
                "max_tokens": 64,
                "temperature": 0.0,
            },
            timeout=30,
        )
        return r.status_code == 200
    except Exception:
        return False


def get_model(base_url: str) -> str:
    try:
        r = requests.get(f"{base_url}/v1/models", timeout=5)
        models = r.json().get("data", [])
        if models:
            return models[0]["id"]
    except Exception:
        pass
    return "unknown"


def run_phase(base_url: str, model: str, rps: int, duration: int, label: str):
    print(f"\n{'='*60}")
    print(f"  PHASE: {label}")
    print(f"  Time:  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}")

    interval = 1.0 / max(rps, 1)
    stop_at = time.monotonic() + duration
    sent = 0
    ok = 0
    lock = threading.Lock()

    def worker():
        nonlocal sent, ok
        success = send_request(base_url, model)
        with lock:
            sent += 1
            if success:
                ok += 1

    while time.monotonic() < stop_at:
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        time.sleep(interval)

    time.sleep(1)  # allow in-flight requests to finish
    print(f"  Done: {sent} requests sent, {ok} succeeded ({ok/max(sent,1)*100:.0f}%)")


def main():
    parser = argparse.ArgumentParser(description="vllm-cost-meter load simulation")
    parser.add_argument("--base-url", default="http://localhost:8000",
                        help="vLLM server URL (default: http://localhost:8000)")
    parser.add_argument("--phase-duration", type=int, default=None,
                        help="Override duration for all phases in seconds")
    parser.add_argument("--skip-confirm", action="store_true",
                        help="Skip the press-Enter confirmation (for automated runs)")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  vllm-cost-meter Load Simulation")
    print(f"  Target: {args.base_url}")
    print(f"{'='*60}")
    print()

    print("Checking vLLM connection...")
    model = get_model(args.base_url)
    if model == "unknown":
        print(f"WARNING: Could not reach {args.base_url}/v1/models — is vLLM running?")
    else:
        print(f"Model: {model}")

    print()
    print("This simulation sweeps concurrency so C_eff swings over time, per")
    print("the paper 'Beyond Per-Token Pricing: A Concurrency-Aware Cost")
    print("Framework for Self-Hosted LLM Inference'.")
    print()
    print("Phases:")
    for name, rps, dur, desc in PHASES:
        d = args.phase_duration or dur
        print(f"  {name:12s} {rps:3d} rps × {d}s  — {desc}")
    print()
    print("Run vllm-cost-meter in another terminal to see cost change live:")
    print("  vllm-cost-meter --gpu-hourly-cost 6.98 --window 2 --compare-api")
    print()

    if not args.skip_confirm:
        input("Press Enter to start simulation…")

    for name, rps, duration, label in PHASES:
        d = args.phase_duration or duration
        run_phase(args.base_url, model, rps, d, label)
        time.sleep(2)  # brief pause between phases

    print(f"\n{'='*60}")
    print("  Simulation complete.")
    print("  Check vllm-cost-meter for final state.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
