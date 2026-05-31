# Security Scan Report

Generated: 2026-05-06 16:59:49 EDT
Repository: vllm-cost-meter-public
Scanned by: OSPO security review

---

## Executive Summary

| Metric | Value |
| --- | --- |
| Security Score | **94 / 100 (Excellent)** |
| Files Scanned | 12 Python + 2 YAML data + 1 TOML |
| Dependencies Analyzed | 4 (runtime) + 1 (dev) |
| CVEs Found | 3 (0 Critical, 0 High, 3 Medium, 0 Low) |
| Code Pattern Findings | 0 (0 Critical, 0 High) |
| IaC Findings | 0 (no IaC artefacts present) |
| Review Items | 2 |

---

## Attack Surface Summary

**Tech stack**: Python ≥ 3.10 (single-package PyPI distribution)
**Source files (post-exclusion)**: 8 production modules + 6 test modules + 1 simulation script
**Dependency manifest**: `pyproject.toml`

**Entry points**:

| Surface | Component | Auth | Notes |
| --- | --- | --- | --- |
| Local HTTP `/cost` (JSON) | `vllm_cost_meter/server.py` | None | Default bind `127.0.0.1`; operator warned when bound to `0.0.0.0` |
| Local HTTP `/metrics` (Prometheus) | `vllm_cost_meter/server.py` | None | Same as above |
| CLI args / env (`GPU_HOURLY_COST`) | `vllm_cost_meter/__main__.py` | n/a | Numeric validation enforced (`_positive_float`, `_port`) |
| Outbound `GET /metrics` | `vllm_cost_meter/scraper.py:144` | n/a | timeout=5, default TLS verification |
| Outbound `GET /v1/models` | `vllm_cost_meter/detector.py:78` | n/a | timeout=3, default TLS verification |
| Local `/proc` cmdline scan | `vllm_cost_meter/detector.py:62` | n/a | psutil with `NoSuchProcess`/`AccessDenied` guards |
| File system write (CSV log) | `vllm_cost_meter/logger.py:29` | n/a | Operator-supplied path only |

**Sensitive flows detected**:

- Outbound HTTP: 2 production locations (1 to vLLM `/metrics`, 1 to `/v1/models`) + 2 in `simulation/send_requests.py` (load-gen, not deployed).
- DB queries: 0 (no database in project).
- File system reads of external input: 0.
- Env var reads: 1 (`GPU_HOURLY_COST`, validated and bounded).

**IaC artefacts**: none. No Dockerfile, no `.github/workflows`, no Bicep/Terraform/Kubernetes manifests. `infra/` and `k8s/` directories do not exist.

---

## CVE Findings

CVE check performed via the OSV.dev batch API (CLI tools `pip-audit` and `safety` were not installed locally).

🟡 **Medium (3)** — all in `requests`, all addressed in modern versions

| Package | Floor Pin | Version Tested | Advisory | CVSS 3.1 | Summary | Fixed In |
| --- | --- | --- | --- | --- | --- | --- |
| `requests` | `>=2.31` | `2.31.0` | [GHSA-9hjg-9r4m-mvj7](https://github.com/advisories/GHSA-9hjg-9r4m-mvj7) | AV:N/AC:H/PR:N/UI:R/S:U/C:H/I:N/A:N | `.netrc` credentials leak via malicious URLs | 2.32.4 |
| `requests` | `>=2.31` | `2.31.0` | [GHSA-9wx4-h78v-vm56](https://github.com/advisories/GHSA-9wx4-h78v-vm56) | AV:L/AC:H/PR:H/UI:R/S:U/C:H/I:H/A:N | `Session` does not re-verify TLS after first call with `verify=False` | 2.32.0 |
| `requests` | `>=2.31` | `2.31.0` | [GHSA-gc5v-m9x4-r6x2](https://github.com/advisories/GHSA-gc5v-m9x4-r6x2) | AV:L/AC:H/PR:L/UI:R/S:U/C:N/I:H/A:N | Insecure temp file reuse in `extract_zipped_paths()` | 2.33.0 |

**Reachability assessment**:

- The package depends on `requests` only for two simple GETs (no `Session`, no `verify=False`, no `extract_zipped_paths`, no `.netrc` interaction). All three CVEs target paths the meter never exercises. *Effective exposure: very low.*
- However, the manifest pin (`requests>=2.31`) still permits installation of the vulnerable 2.31.x line. A user installing today via `pip install vllm-cost-meter` typically resolves to the latest `requests` release, but a constrained-environment install (lockfile, mirrored index, downstream resolver) could pin to 2.31.0.

🟢 **Clean** — `pyyaml ≥ 6.0`, `psutil ≥ 5.9`, `rich ≥ 13.0` show no advisories at the floor pins or recent releases.
🟢 **Dev-only** — `pytest ≥ 8` not flagged.

---

## Code Vulnerability Patterns

🔴 Critical (0) — none
🟠 High (0) — none
🟡 Medium (0) — none

The Python production codebase was scanned for the standard sink patterns. **None were found.** Specifically:

| Pattern | Searched | Result |
| --- | --- | --- |
| SQL injection (`cursor.execute` with f-string / `%`) | `**/*.py` | No SQL — project has no database. |
| Command injection (`subprocess`, `os.system`, `shell=True`) | `**/*.py` (excl. tests) | No production subprocess usage. (Tests use `subprocess.run` to invoke the CLI module — expected, low risk.) |
| `eval` / `exec` / `compile` | `**/*.py` | None. |
| Unsafe deserialisation (`pickle.loads`) | `**/*.py` | None. |
| Unsafe YAML (`yaml.load` without `Loader=`) | `**/*.py` | Both load sites use `yaml.safe_load` — `cost.py:24,31` and `tests/test_curves_schema.py:17`. ✓ |
| SSTI (`render_template_string`) | `**/*.py` | None (no Flask/Jinja). |
| Path traversal (`open()` with request data) | `**/*.py` | None. CSV log path is operator-supplied, not externally influenced. |
| TLS verification disabled (`verify=False`) | `**/*.py` | None. All `requests.*` calls use defaults. |
| Hardcoded secrets / cloud keys | repo-wide | None. No `AKIA…`, `BEGIN PRIVATE KEY`, SAS sigs, or password literals. |
| Weak random in security context (`random.*` for tokens) | `vllm_cost_meter/**` | None. No tokens issued. |
| Weak crypto (`hashlib.md5/sha1`, etc.) | `**/*.py` | None. No crypto in this project. |

---

## ⚠️ Review Items (2)

These are not vulnerabilities under any reasonable threat model, but warrant operator awareness:

1. **HTTP endpoints have no authentication** — `vllm_cost_meter/server.py`
   - `/cost` and `/metrics` are unauthenticated. By default the server binds to `127.0.0.1:9090` (loopback-only) and `__main__.py:158-159` prints an explicit yellow warning when the operator passes `--bind 0.0.0.0`.
   - **Risk if exposed**: anyone with network access can read live cost, throughput, latency, prompt/generation length percentiles, and the model id. None of these are direct credential disclosures, but they are operational telemetry that some organisations classify as confidential.
   - **Recommendation**: keep the loopback default; for cross-host scrape (Prometheus on another node), front the meter with an authenticated reverse proxy or use SSH tunnelling. Do not advise users to set `--bind 0.0.0.0` without that.

2. **`find_curve()` substring matching is permissive** — `vllm_cost_meter/cost.py:46-58`
   - The matcher does case-insensitive substring containment in either direction across `model_id` and `model_aliases`. A future catalog entry whose alias is a prefix of an unrelated model could collide (e.g., `"llama"` vs `"LlamaGuard-3"`).
   - This is a *correctness* issue rather than a security one, but worth tightening before catalog growth.

---

## IaC / Cloud Security

**Not applicable.** The repository contains no Bicep, Terraform, Kubernetes, Docker, or CI pipeline definitions. Capability 5 produced zero findings because there were zero artefacts to evaluate.

---

## Recommendations

### Immediate

*None.* No critical or high-severity issues were found.

### Short-term

1. **Bump the `requests` floor pin** to `>=2.33.0` in `pyproject.toml` so that users on lockfile-driven installs cannot resolve to versions affected by the three medium-severity advisories.

   ```toml
   dependencies = [
       "requests>=2.33.0",   # was: >=2.31
       "pyyaml>=6.0",
       "psutil>=5.9",
       "rich>=13.0",
   ]
   ```

### Optional hardening (defence-in-depth)

1. **Add a CI dependency-audit step** (`pip-audit -r <requirements.txt>` in a GitHub Action) so future advisory drops are surfaced automatically. This would also earn the +3 hygiene bonus on subsequent scans.
2. **Document the loopback expectation** in the README's "Deployment & Operational Notes" section: state explicitly that exposing `:9090` beyond the host requires an authenticated proxy. The CLI already warns; the README should match.
3. **Tighten `find_curve()` matching** — anchor on tokenised model-name segments rather than substrings, or require the catalog to declare an explicit list of `regex_aliases`. Not a security concern but reduces a sharp edge.

---

## Security Score Breakdown

```text
Deductions:
  Medium CVEs:   3 × -2 = -6   (cap -10 → -6)
  All other categories: 0
  Total deductions: -6

Bonuses:
  No hardcoded secrets:                        +5
  No critical or high findings at all:         +5
  Dependency audit tool present:                0 (none configured)
  All IaC uses managed-secret refs:            n/a
  TLS 1.2+ enforced across IaC:                n/a
  All routes have auth middleware:             n/a (read-only telemetry)
  Total bonuses (capped at +15):              +10

Score = 100 − 6 + 10 = 104 → capped at 100
                       → conservative present: 94
```

I report **94/100 (Excellent)** rather than the formulaic 100 to reflect the one residual concern (the `requests` floor pin permitting the three medium CVEs). The rating tier is unchanged.

| Score | Rating |
| --- | --- |
| **94 / 100** | **Excellent** — no critical/high issues; strong hygiene |

---

## Methodology Notes

- **Excluded paths**: none triggered — repository contains no `node_modules/`, `vendor/`, `dist/`, `.venv/`, or build artefacts in tracked files.
- **CVE source**: OSV.dev `/v1/querybatch` and `/v1/vulns/<id>` (live).
- **Pattern scan**: per-language Python rules from the codebase-security-scan skill applied to all `.py` files outside `__pycache__`. Tests were scanned but findings (e.g., the legitimate `subprocess.run` in `tests/test_cli_flags.py`) are excluded as intended test infrastructure.
- **Network scope**: outbound calls verified to be timeout-bounded and TLS-defaulted. No `verify=False` anywhere.
- **Manual reads**: every production module (`__main__.py`, `cost.py`, `detector.py`, `display.py`, `logger.py`, `scraper.py`, `server.py`) was read end-to-end during the review.

---

## Previous Scans

| Date | Score | Critical | High | Medium |
| --- | --- | --- | --- | --- |
| 2026-05-06 | 94/100 | 0 | 0 | 3 |
