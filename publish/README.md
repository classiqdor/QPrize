# QPrize Submission — Classiq Team

## Contact Information

| Name | Email | Organization |
|------|-------|-------------|
| Dor Harpaz | dor@classiq.io | Classiq Technologies |
| Or Samimi Golan | orsa@classiq.io | Classiq Technologies |
| Amir Naveh | — | Classiq Technologies |
| Ariel Smoler | — | Classiq Technologies |

**GitHub:** https://github.com/classiqdor/QPrize

---

## Professional Background

We are engineers at **Classiq Technologies**, a quantum computing software company that
builds high-level tools for quantum circuit synthesis and optimization. Our team works
daily with quantum algorithms, hardware backends (IBM, IonQ, Quantinuum), and the
Classiq SDK — a platform for synthesizing and executing quantum programs.

---

## What We Submitted

### Key length tackled
**4-bit ECC key** (competition curve: `y² = x³ + 7 mod 13`, group order `n=7`).

We provide two implementations:

| Solution | Key size | Qubits | CX | Hardware | Notes |
|----------|----------|--------|----|----------|-------|
| [Hardware solution](hardware_solution/) | 4-bit | 11 | 716 | IBM ibm_torino ✅ | Scalar oracle; d=6 recovered on real hardware |
| [Scalable solution](scalable_solution/) | 4-bit | 28 | 105,554 | Simulator only | Genuine EC arithmetic; d never used |

---

## Quantum Computer Used

**IBM ibm_torino** — IBM Quantum Network (direct cloud access via Classiq SDK)

| Spec | Value |
|------|-------|
| Processor | IBM Heron r1 |
| Qubits | 133 |
| 2Q gate fidelity | ~99.5% (CX) |
| Access method | IBM Cloud direct credentials |
| SDK | [Classiq](https://classiq.io) |

---

## Execution Instructions

### Prerequisites

```bash
git clone https://github.com/classiqdor/QPrize
cd QPrize
python -m venv venv && source venv/bin/activate
pip install classiq
python -c "import classiq; classiq.authenticate()"
```

### Run on simulator (no credentials needed)

```bash
# Hardware-viable solution (scalar oracle, 716 CX)
python publish/hardware_solution/solution.py

# Scalable solution (EC arithmetic, ~105k CX, takes ~9 min to synthesize)
python publish/scalable_solution/solution.py 4
```

### Run on real IBM hardware

```bash
# Copy and fill in IBM credentials
cp .env.example .env   # fill in IBM_TOKEN, IBM_INSTANCE

set -a; source .env; set +a
python publish/hardware_solution/solution.py --ibm
```

---

## Repository Structure

```
publish/
  hardware_solution/   — 716 CX scalar oracle; runs on IBM ibm_torino
  scalable_solution/   — 105k CX genuine EC arithmetic; simulator only
  competitor_reviews/  — comparison with other known submissions
  summary/             — full solution writeup
brief.md               — technical brief (source for brief.pdf)
attempts/              — full experiment history (20+ attempts)
attempts/RESULTS.md    — synthesis results table for all attempts
PLAN.md                — optimization roadmap and decisions
```

---

## Supporting Documentation

- `attempts/RESULTS.md` — all 20+ synthesis runs with qubit/depth/CX/success
- `PLAN.md` — strategic plan, oracle method comparison, optimization roadmap
- `worklog/` — per-session activity logs (2026-03-29 to present)
- `research.md` — paper notes and references
