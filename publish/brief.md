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

**Method A — Scalar Oracle** (hardware-viable): Oracle register holds scalar index `k ∈ Z_n`.
Reduces to controlled modular additions — O(var_len·log²n) gates.
4-bit result: **11 qubits, 716 CX** — ran on IBM ibm_torino, recovered d=6 ✅

**Method B — EC Coordinate Oracle** (scalable, simulator only): Oracle register holds
`(x, y) ∈ F_p × F_p`. Applies quantum EC point additions using slope formula mod p
(Roetteler 2017, Algorithm 1). `d` is never used anywhere in the circuit.
4-bit result: **28 qubits, 105,554 CX** — Classiq simulator, recovered d=6 ✅

---

## Optimizations

**Profiling** revealed `modular_square` (2,852 CX) dominates Method B cost. Replacing it
with a 1D lookup table `sq_lookup` (120 CX, 24× cheaper) reduced total CX from 130k → 105k.
Key finding: 1D lookups (single `Const[QNum]` input) synthesize efficiently; 2D lookups
require `bind` which doubles overhead in `within_apply` due to uncomputation.
**20+ optimization attempts** explored: projective coordinates, schoolbook multipliers,
windowed oracles, semiclassical QFT, truncated registers. Full log in `RESULTS.md`.

---

## Hardware Execution & Results

| Metric | Value |
|--------|-------|
| Hardware | IBM ibm_torino (Heron r1, 133 qubits) |
| Circuit | 4-bit, 11 qubits, 716 CX, depth 1050 |
| Shots | 1,000 | Fidelity estimate | ~2.8% (0.995^716) |
| Synthesis + execution | 14s + 24s = 38s total |
| Result | d=6 recovered ✅ (Classiq Job ID: 8f36bc48-6ee8-4a56-968b-4299dc0f316b) |

All invertible `(x1_r, x2_r)` pairs consistently recover `d=6` — no engineered post-processing:

```
 x1_r  x2_r  d   counts
    5     5   6      24   ████████████████████████
    1     1   6      23   ███████████████████████
    6     6   6      20   ████████████████████
    2     2   6      16   ████████████████
  ...   ...   6     ...   (all invertible pairs give d=6)
```

---

## Limitations

**Method A:** Oracle constants require enumerating all `n` group elements classically
(O(n) work). Infeasible for n ≈ 2²⁵⁶ — competition-scale demonstration only.

**Method B:** `sq_lookup` and `modular_inverse_lookup` each have `p` entries — feasible
for p=13, not for p ≈ 2²⁵⁶. Replacing them with Kaliski modular inverse and QROM
arithmetic would make the circuit fully scalable.

---

## References

1. Roetteler, Naehrig, Svore, Lauter — *Quantum Resource Estimates for ECDLP* (2017)
2. Haner, Jaques, Naehrig, Roetteler, Soeken — *Improved Quantum Circuits for ECDLP* (2020)
3. Classiq SDK — https://docs.classiq.io
