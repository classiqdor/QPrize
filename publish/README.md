# QPrize Submission — Classiq Team

## Contact Information

| Name | Email | Organization |
|------|-------|-------------|
| Amir Naveh | amir@classiq.io | Classiq Technologies |
| Ariel Smoler | ariel@classiq.io | Classiq Technologies |
| Dor Harpaz | dor@classiq.io | Classiq Technologies |
| Or Samimi Golan | orsa@classiq.io | Classiq Technologies |

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
| [Hardware solution](hardware_solution/) | 4-bit | 11 | 716 | IBM ibm_torino, IonQ Forte-1, IBM ibm_pittsburgh, Rigetti Ankaa-3 ✅ | Scalar oracle; d=6 recovered on 4 devices across 3 vendors |
| [Scalable solution](scalable_solution/) | 4-bit | 28 | 105,554 | Simulator only | Genuine EC arithmetic; d never used |

---

## Quantum Computers Used

The 4-bit circuit was executed on four devices across three vendors:

| Device | Vendor | Type | Qubits | Access |
|--------|--------|------|--------|--------|
| IBM ibm_torino (Heron r1) | IBM Quantum | Superconducting | 133 | IBM Cloud direct |
| IonQ Forte-1 | IonQ | Trapped-ion | 36 | Classiq SDK |
| IBM ibm_pittsburgh | IBM Quantum | Superconducting | 127 | IBM Cloud direct |
| Rigetti Ankaa-3 | Rigetti / AWS Braket | Superconducting | 84 | AWS Braket |

All runs used the same circuit: **11 qubits, 716 CX, depth 1050**. All recovered d=6 ✅.

---

## Execution Instructions

### Prerequisites

```bash
# Clone repo
git clone https://github.com/classiqdor/QPrize
cd QPrize

# Install classiq
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
cp .env.example .env
# fill in IBM_TOKEN, IBM_INSTANCE

set -a; source .env; set +a
python publish/hardware_solution/solution.py --ibm
```

---

## Repository Structure

```
publish/
  hardware_solution/   — 716 CX scalar oracle; verified on IBM, IonQ, Rigetti
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
