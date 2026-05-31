# tests/test_cli_flags.py
import subprocess
import sys


def run_cli(*args, env=None):
    return subprocess.run(
        [sys.executable, "-m", "vllm_cost_meter"] + list(args),
        capture_output=True, text=True, env=env, timeout=5,
    )


def test_compare_api_without_mismatch_flag_refuses():
    # With --compare-api but no --accept-slo-mismatch, should exit nonzero
    # and mention the fallacy before even trying to scrape.
    result = run_cli("--gpu-hourly-cost", "6.98", "--compare-api")
    assert result.returncode != 0
    combined = (result.stderr or "") + (result.stdout or "")
    assert "accept-slo-mismatch" in combined.lower() or "slo" in combined.lower()


def test_slo_flags_accepted():
    # Smoke: parser accepts the flags without crashing at parse time.
    result = run_cli(
        "--gpu-hourly-cost", "6.98",
        "--slo-ttft-p99-ms", "300",
        "--slo-tpot-p99-ms", "50",
        "--slo-e2el-p99-ms", "5000",
        "--help",
    )
    assert result.returncode == 0
    assert "--slo-ttft-p99-ms" in result.stdout
