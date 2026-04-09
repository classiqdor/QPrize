# QPrize — Shor's ECDLP on Quantum Hardware

**Team:** Classiq Technologies
**Submission deadline:** April 5, 2026

---

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

We are engineers at [Classiq Technologies](https://classiq.io), a quantum computing
software company that builds tools for high-level quantum circuit synthesis and optimization.
Our team works daily with quantum algorithms, circuit synthesis, and hardware backends
including IBM Quantum, IonQ, and Quantinuum.

---

## Key Length Tackled

**4-bit ECC key** — competition curve `y² = x³ + 7 mod 13`, group order `n = 7`, private key `d = 6`.

We provide two implementations at different points on the cost/legitimacy spectrum:

| Solution | Qubits | CX | Hardware | Result |
|----------|--------|----|----------|--------|
| [Scalar oracle](publish/hardware_solution/) | 11 | 716 | IBM ibm_torino, IonQ Forte-1, IBM ibm_pittsburgh, Rigetti Ankaa-3 ✅ | d=6 recovered |
| [EC arithmetic oracle](publish/scalable_solution/) | 28 | 105,554 | Simulator only | d=6 recovered |

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
# Hardware-viable circuit (716 CX, scalar oracle)
python publish/hardware_solution/solution.py

# Scalable genuine-ECDLP circuit (~105k CX, takes ~9 min to synthesize)
python publish/scalable_solution/solution.py 4
```

### Run on real IBM hardware

```bash
cp .env.example .env
# fill in IBM_TOKEN, IBM_INSTANCE
set -a; source .env; set +a
python publish/hardware_solution/solution.py --ibm
```

---

## Submission Contents

```
publish/
  hardware_solution/    — 716 CX scalar oracle; verified on IBM, IonQ, Rigetti
  scalable_solution/    — 105k CX genuine EC arithmetic (Roetteler 2017); simulator
  competitor_reviews/   — comparison with other known submissions
  summary/              — full solution writeup
  brief.md              — technical brief (source for brief.pdf)
attempts/RESULTS.md     — all 20+ synthesis runs (qubits, depth, CX, success)
PLAN.md                 — optimization roadmap and decision log
worklog/                — per-session activity logs
```

---

## Algorithm Summary

We implement Shor's ECDLP algorithm using two-register quantum phase estimation:

1. Prepare superposition `|+⟩^{2·var_len}` over registers `x1`, `x2`
2. Oracle: `ecp = P₀ + x1·G − x2·Q`
3. Inverse QFT to extract the period
4. Recover `d = −x2_r · x1_r⁻¹ mod n`

Full technical details in [`publish/brief.md`](publish/brief.md) and [`publish/summary/summary.md`](publish/summary/summary.md).

