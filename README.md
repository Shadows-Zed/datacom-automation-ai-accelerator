# Datacom — Automation AI Accelerator: From Co-pilot to Autonomous Agent

<p align="left">
  <strong>English</strong> | <a href="README.zh-CN.md">简体中文</a>
</p>

[![CI](https://github.com/Shadows-Zed/datacom-automation-ai-accelerator/actions/workflows/ci.yml/badge.svg)](https://github.com/Shadows-Zed/datacom-automation-ai-accelerator/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Dependencies](https://img.shields.io/badge/Runtime%20Dependencies-Zero%20(Stdlib)-059669)
![Tests](https://img.shields.io/badge/Automated%20Tests-24%2F24%20Passing-16A34A)
![Quiz Score](https://img.shields.io/badge/Completion%20Quiz-10%2F10%20(100%25)-0057B8)
![License](https://img.shields.io/badge/License-MIT-slate)

End-to-end engineering portfolio for the **Datacom Automation AI Accelerator** virtual experience on Forage—demonstrating the progression from **AI-assisted debugging (Pilot)** to **spec-driven full-stack architecture (Architect)** and **autonomous business-process agent design (Strategic Partner)**.

```mermaid
flowchart LR
    T1["<b>Task 1 · Pilot</b><br/>AI-Powered Debugging & Refactoring<br/>16 Tests · 3.47x Metrics · 152.5x Lookup"]
    T2["<b>Task 2 · Architect</b><br/>Spec-Driven Full-Stack Kudos Portal<br/>SQLite · REST · RBAC · Audit Log"]
    T3["<b>Task 3 · Strategic Partner</b><br/>OrderBot Autonomous AI Agent<br/>3-Slide Pitch · Read-Only PoC"]

    T1 --> T2 --> T3

    style T1 fill:#EFF6FF,stroke:#0057B8,stroke-width:2px,color:#0A2540
    style T2 fill:#F0FDF4,stroke:#059669,stroke-width:2px,color:#064E3B
    style T3 fill:#0A2540,stroke:#0057B8,stroke-width:2px,color:#FFFFFF
```

---

## Repository Overview

| Module | Role | Key Deliverables | Highlights |
|---|---|---|---|
| **[`task1-ai-debugging-refactoring/`](task1-ai-debugging-refactoring/)** | **Pilot** | [`process_data_final.py`](task1-ai-debugging-refactoring/process_data_final.py), [`TEST_CASES.py`](task1-ai-debugging-refactoring/TEST_CASES.py), [`DEBUG_LOG.md`](task1-ai-debugging-refactoring/DEBUG_LOG.md) | Fixed 8 production & hidden data-integrity defects; **13/16 Red → 16/16 Green** TDD; **3.47×** faster metrics & **152.5×** faster exact lookups |
| **[`task2-kudos-spec-driven-app/`](task2-kudos-spec-driven-app/)** | **Architect** | [`SPECIFICATION.md`](task2-kudos-spec-driven-app/SPECIFICATION.md), full-stack Python/SQLite/SPA app, [`test_kudos.py`](task2-kudos-spec-driven-app/test_kudos.py) | Spec-first design refined with Admin Content Moderation (`is_visible`, audit log), RBAC, XSS sanitization, duplicate/rate-limit guards; **8/8** integration tests passing |
| **[`task3-orderbot-agentic-proposal/`](task3-orderbot-agentic-proposal/)** | **Strategic Partner** | [`OrderBot_Automation_Proposal.pdf`](task3-orderbot-agentic-proposal/OrderBot_Automation_Proposal.pdf), [`build_slides_pdf.py`](task3-orderbot-agentic-proposal/build_slides_pdf.py) | Conceptual autonomous agent (**OrderBot**) for Email + Salesforce + Google Sheets order workflow (`< 5 min`, `99.5%` target) & low-risk **Read-Only PoC** roadmap |
| **[`scripts/run_all_checks.py`](scripts/run_all_checks.py)** | **Verification** | Unified CI & live benchmark runner | Runs Task 1 Red→Green tests, Task 2 E2E tests, Task 3 syntax checks, and 10k/50k benchmark in one command |
| **[`assets/`](assets/)** | **Proof & Visuals** | [`datacom_completion_certificate.pdf`](assets/datacom_completion_certificate.pdf), UI & slide PNG previews | Verified completion certificate (**100% / 10/10** final assessment) & high-res visual previews |

---

## Module Highlights

### 1. AI-Powered Debugging & Refactoring (`task1-ai-debugging-refactoring/`)
- **Root-Cause & Empirical Discovery:** Beyond fixing the fragile `next(iter(...)).keys()` CSV export crash and silent failure masking in `main()` indicated by `error.log`, live execution against the sample CSVs uncovered hidden trailing-whitespace category splitting (`"books "` vs `"books"`), unknown-customer average-value skew, binary floating-point drift (`0.10 + 0.20 = 0.30000000000000004`), missing `customer_id` in summary reports, and broken `customer_id` search.
- **Measured Performance Gains (10,000 customers · 50,000 transactions):**

| Operation | Legacy (`process_data.py`) | Refactored (`process_data_final.py`) | Speedup |
|---|---:|---:|---:|
| `calculate_customer_metrics()` (×20) | `0.1195s` | `0.0344s` | **3.47× faster** |
| `find_matches()` substring (×500) | `0.3701s` | `0.1215s` | **3.05× faster** |
| `find_matches()` exact dict lookup (×500) | `0.3701s` | `0.0024s` | **152.5× faster** |

### 2. Spec-Driven Full-Stack Kudos Portal (`task2-kudos-spec-driven-app/`)
- **Specification-First Workflow:** Authored [`SPECIFICATION.md`](task2-kudos-spec-driven-app/SPECIFICATION.md) before writing code, adding Administrator content moderation (`HIDE`, `RESTORE`, `DELETE`), moderation metadata (`is_visible`, `moderated_by`, `moderated_at`, `reason_for_moderation`), and an immutable `moderation_audit_log`.
- **Production-Grade Safeguards (Zero External Dependencies):** Salted `PBKDF2-HMAC-SHA256` authentication, server-side RBAC (`403 Forbidden` on non-admin moderation attempts), self-kudos DB `CHECK` constraint, 5-minute duplicate guard (`409 Conflict`), per-user sliding-window rate limiter (`429 Too Many Requests`), HTML angle-bracket neutralization + DOM `textContent` rendering against XSS, and responsive desktop/mobile UI.

<p align="center">
  <img src="assets/kudos_portal_ui.png" alt="Datacom Kudos Portal UI showcasing composer, live feed, admin moderation, and audit log" width="90%" />
  <br />
  <em>Live Kudos Portal UI (Admin View): Colleague Composer, Recent Feed, Moderated "Hidden" Card with Reason, and Immutable Audit Log</em>
</p>

### 3. OrderBot — Agentic AI Business Proposal (`task3-orderbot-agentic-proposal/`)
Designed a 3-slide executive pitch translating technical agent architecture (Goal, Perception, Planning, Action, Memory/Learning) into clear business outcomes and a zero-risk **3-week Read-Only Proof of Concept**:

<table>
  <tr>
    <td><img src="assets/slide_1_problem.png" alt="Slide 1: The Problem" /></td>
    <td><img src="assets/slide_2_solution.png" alt="Slide 2: OrderBot Solution" /></td>
    <td><img src="assets/slide_3_impact.png" alt="Slide 3: Impact & Roadmap" /></td>
  </tr>
  <tr>
    <td align="center"><b>Slide 1:</b> Current Manual Bottleneck</td>
    <td align="center"><b>Slide 2:</b> OrderBot Autonomous Architecture</td>
    <td align="center"><b>Slide 3:</b> Business Impact &amp; Read-Only PoC</td>
  </tr>
</table>

---

## Key Engineering Decisions & Trade-offs

- **Benchmark-Driven Second Iteration (`Decimal` vs. `math.fsum`):** In Task 1, retaining exact `Decimal` accumulation during transaction ingestion while replacing repeated `Decimal(str(...))` conversions inside `calculate_customer_metrics()` with C-accelerated Shewchuk summation (`math.fsum`) more than doubled metrics throughput (**1.44× → 3.47×**) without sacrificing financial accuracy.
- **Transport-Independent HTTP Router (`KudosApp`):** In Task 2, separating HTTP routing/business dispatch (`KudosApp.handle`) from the TCP socket adapter (`KudosHTTPServer`) enabled deterministic, sub-second end-to-end API integration testing (`test_kudos.py`) with zero port contention and clean portability to WSGI/ASGI servers.
- **Zero Third-Party Runtime Dependencies:** Choosing Python 3.11+ standard library + SQLite WAL mode ensures any reviewer or CI runner can verify all 24 tests and boot the full web app immediately with zero `pip install` friction.
- **Risk-First Agent Rollout (`Read-Only PoC`):** In Task 3, proposing a 3-week read-only shadow phase before any write permissions gives Operations empirical proof of `≥ 99.5%` accuracy while maintaining strict human-in-the-loop escalation on exceptions.

---

## Quick Start & Verification (Zero `pip install` Required)

Requires **Python 3.11+** only.

### One-Command Full Verification & Benchmark
```bash
python3 scripts/run_all_checks.py
```

### Run Individual Suites
```bash
# Task 1 — Verify all 16 tests pass on refactored pipeline
PYTHONPATH=task1-ai-debugging-refactoring \
  python3 -m unittest -v task1-ai-debugging-refactoring/TEST_CASES.py

# Task 1 — (Optional) Confirm original bugs reproduce on legacy baseline (13 expected failures)
PYTHONPATH=task1-ai-debugging-refactoring DATA_PROCESSOR_MODULE=process_data \
  python3 -m unittest -v task1-ai-debugging-refactoring/TEST_CASES.py

# Task 2 — Run all 8 end-to-end API, RBAC, moderation & security tests
PYTHONPATH=task2-kudos-spec-driven-app \
  python3 -m unittest -v task2-kudos-spec-driven-app/test_kudos.py
```

### Launch the Kudos Web Application Locally
```bash
python3 task2-kudos-spec-driven-app/app.py
# Open http://127.0.0.1:8000
# Demo Employee: alice / demo123  |  Demo Admin: admin / admin123
```

---

## License

This project is released under the [MIT License](LICENSE).
