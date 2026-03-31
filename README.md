# QPrize — Shor's ECDLP on Quantum Hardware

**Team:** Classiq Technologies
**Submission deadline:** April 5, 2026

---

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
| [Scalar oracle](publish/hardware_solution/) | 11 | 716 | IBM ibm_torino ✅ | d=6 recovered |
| [EC arithmetic oracle](publish/scalable_solution/) | 28 | 105,554 | Simulator only | d=6 recovered |

---

## Quantum Computer Used

**IBM ibm_torino** (IBM Quantum Network)

| Spec | Value |
|------|-------|
| Processor | IBM Heron r1 |
| Total qubits | 133 |
| 2Q gate fidelity | ~99.5% (CX) |
| Access method | Direct IBM Cloud credentials via Classiq SDK |

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
# Hardware-viable circuit (716 CX, scalar oracle)
python publish/hardware_solution/solution.py

# Scalable genuine-ECDLP circuit (~105k CX, takes ~9 min to synthesize)
python publish/scalable_solution/solution.py 4
```

### Run on real IBM hardware

```bash
cp .env.example .env   # fill in IBM_TOKEN and IBM_INSTANCE
set -a; source .env; set +a
python publish/hardware_solution/solution.py --ibm
```

---

## Submission Contents

```
publish/
  hardware_solution/    — 716 CX scalar oracle; verified on IBM ibm_torino
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

