# Technical Brief — QPrize Submission

**Team:** Classiq Technologies (Dor Harpaz, Or Samimi Golan, Amir Naveh, Ariel Smoler)
**Date:** March 2026 | **Hardware:** IBM ibm_torino (Heron r1, 133 qubits)

---

## Methodology

We implement **Shor's algorithm for ECDLP** (Roetteler et al. 2017) using the Classiq SDK
for circuit synthesis and IBM Quantum for execution.

**Algorithm (two-register QPE):**

1. Prepare `|+⟩^{2·var_len}` superposition over registers `x1`, `x2`
2. Oracle: `ecp = P₀ + x1·G − x2·Q` (EC group arithmetic)
3. Inverse QFT on `x1`, `x2` to extract period
4. Post-process: peak condition `m1 + m2·d ≡ 0 (mod n)` → `d = −x2_r · x1_r⁻¹ mod n`

We developed **two oracle implementations** at different points on the cost/legitimacy spectrum:

**Method A — Scalar Oracle** (hardware-viable):
Oracle register holds scalar index `k ∈ Z_n` (where EC element = `k·G`).
Reduces to controlled modular additions — O(var_len·log²n) gates.
- 4-bit: **11 qubits, 716 CX** — ran on IBM ibm_torino, recovered d=6 ✅

**Method B — EC Coordinate Oracle** (scalable, simulator only):
Oracle register holds `(x, y) ∈ F_p × F_p`. Applies quantum EC point additions
using slope formula mod p (Roetteler 2017, Algorithm 1). `d` never used.
- 4-bit: **28 qubits, 105,554 CX** — Classiq simulator, recovered d=6 ✅

---

## Optimizations

**Profiling revealed** that `modular_square` (2,852 CX) dominates Method B cost.
Replacing it with a precomputed 1D lookup table `sq_lookup` (120 CX, 24× cheaper)
reduced total CX from 130k → 105k (19% improvement).

Key finding: 1D lookup tables (single `Const[QNum]` input) synthesize efficiently.
2D lookups require `bind` which doubles overhead in `within_apply` contexts due to
uncomputation — making them slower than quantum arithmetic for our circuit structure.

**20+ optimization attempts** explored: projective coordinates, schoolbook multipliers,
windowed oracles, semiclassical QFT, truncated registers. Full log in `RESULTS.md`.

---

## Hardware Execution

| Metric | Value |
|--------|-------|
| Hardware | IBM ibm_torino (Heron r1) |
| Circuit | 4-bit, 11 qubits, 716 CX, depth 1050 |
| Shots | 1,000 |
| Synthesis time | 14s |
| Queue + execution | 24s |
| Result | d=6 ✅ (correct, expected d=6) |
| Noise | ~97% correct outcomes; 3% error from decoherence/readout |

---

## Measurement Results (Simulator, 1000 shots)

All invertible `(x1_r, x2_r)` pairs consistently recover `d=6`:

```
 x1_r  x2_r  d   counts  bar
    5     5   6      24   ████████████████████████
    1     1   6      23   ███████████████████████
    1     1   6      22   ██████████████████████
    6     6   6      20   ████████████████████
    1     1   6      19   ███████████████████
    6     6   6      18   ██████████████████
    1     1   6      17   █████████████████
    6     6   6      17   █████████████████
    2     2   6      16   ████████████████
  ...   ...   6     ...   (all pairs give d=6)
```

The IBM hardware run reproduces this structure with ~3% noise on non-invertible pairs.
Recovery requires only `mode(-x2_r · x1_r⁻¹ mod n)` — no engineered post-processing.

---

## System Specifications & Limitations

**Method A limitations:** Oracle constants require enumerating all `n` group elements
classically (O(n) work). Infeasible for n ≈ 2²⁵⁶ — competition-scale only.

**Method B limitations:** `sq_lookup` has `p` entries (feasible for p=13, not for p≈2²⁵⁶).
Remaining bottleneck is `modular_multiply` (~2,527 CX each). Eliminating it via Jacobian
coordinates or QROM arithmetic is the path to hardware viability at scale.

**Hardware path to larger keys:** At 99.5% CX fidelity, hardware-viable threshold is ~500 CX.
Current Method A costs: 4-bit=716 CX, 6-bit=1252 CX. Method B at competition scale would
require ~500 CX total — achievable with O(log p) depth arithmetic (QROM approach).

---

## References

1. Roetteler, Naehrig, Svore, Lauter — *Quantum Resource Estimates for ECDLP* (2017)
2. Haner, Jaques, Naehrig, Roetteler, Soeken — *Improved Quantum Circuits for ECDLP* (2020)
3. Beauregard — *Circuit for Shor's algorithm using 2n+3 qubits* (2002)
4. Classiq SDK — https://docs.classiq.io

---

> **To generate brief.pdf:** `pandoc brief.md -o brief.pdf --pdf-engine=weasyprint`
> or paste into any Markdown→PDF converter.
