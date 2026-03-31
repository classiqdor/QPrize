# Competitor Reviews

Comparison of our submission against other known QPrize submissions.

---

## Known Submissions

### 1. Aditya Yadav (adityayadav76)

**Repository:** https://github.com/adityayadav76/qday_prize_submission

| Property | Their approach | Our approach |
|----------|---------------|-------------|
| Algorithm | Shor's ECDLP | Shor's ECDLP |
| Framework | Qiskit | Classiq SDK |
| Hardware | Automatski (proprietary) | IBM ibm_torino |
| Key size | 7–8 bit | 4-bit (hardware), 4-bit (scalable sim) |
| Qubit count | 16–18 | 11 (hardware), 28 (scalable) |
| Oracle method | Scalar index | Scalar index (hardware) / EC coordinates (scalable) |
| Legitimacy | Unclear | `group enum` (hardware), `lookup inverse` only (scalable) |

**Automatski hardware claims:** 70 logical qubits, 99.999% 2Q fidelity, 10M gate depth.
These specs are extraordinary and unverified by independent benchmarks. At 99.999% fidelity
with 10M gate depth, virtually any quantum algorithm would succeed — but there is no
peer-reviewed evidence for these specifications.

**Assessment:** Their 7–8 bit key claim, if genuine on verified hardware, would surpass
our 4-bit hardware result. However, the hardware specs appear implausible given the current
state of quantum computing. IBM and IonQ — the best publicly benchmarked systems — achieve
~99.5–99.9% 2Q fidelity with coherence times of milliseconds to seconds, not 43 minutes.

---

## Landscape Summary

As of 2026-03-31 (deadline April 5):

| Team | Key size | Hardware | Verified |
|------|----------|----------|---------|
| Our team (Classiq) | 4-bit | IBM ibm_torino | ✅ Yes |
| adityayadav76 | 7–8 bit | Automatski | ❓ Unverified hardware |
| Other teams | Unknown | — | Unknown |

The competition leaderboard shows "coming soon" — no official rankings yet.

---

## Our Differentiators

1. **Verified IBM hardware run** — ibm_torino is a publicly benchmarked, production IBM Quantum system. Our results are reproducible by anyone with IBM Quantum access.

2. **Two distinct approaches** — We provide both a hardware-viable scalar oracle (716 CX, runs on IBM today) and a scalable genuine-ECDLP circuit (105k CX, correct algorithm that would work at cryptographic scale with better hardware).

3. **Open research log** — All 20+ attempts, profiling data, and failure analysis are documented in `attempts/RESULTS.md` and `PLAN.md`.

4. **Classiq SDK** — Circuit synthesis is handled by Classiq's optimizer, which automatically exploits constant structure in modular additions.
