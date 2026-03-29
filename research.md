# Research Notes

## Key References

### Primary Implementation
- [Classiq ECDLP notebook](https://github.com/Classiq/classiq-library/blob/main/algorithms/number_theory_and_cryptography/elliptic_curves/elliptic_curve_discrete_log.ipynb) — our starting point; check its references section
- Classiq SDK: `modular_arithmetic` module (built-in: `modular_add_constant_inplace`, `modular_add_qft_space`, `qft`, etc.)

### Competition
- [curves.txt](https://www.qdayprize.org/curves.txt) — all curves use `y^2 = x^3 + 7` over `F_p` (i.e. `a=0`, `b=7`)

---

## What the Colleague Already Did

Group-index encoding: instead of storing EC points as `(x,y)` pairs, store them as scalar `k` meaning `k·G`. The full oracle becomes controlled modular additions of precomputed constants — no quantum modular inversion needed.

**Circuit formula:**
```
ecp_idx = INITIAL_IDX + Σᵢ x1[i]·2ⁱ + Σᵢ x2[i]·(n−d)·2ⁱ  (mod n)
```
All constants precomputed classically from known `n` and `d`.

**Results:**

| Variant | Bits | Qubits | CX | Fidelity | Status |
|---|---|---|---|---|---|
| Ripple-carry | 4 | 11 | 716 | ~2.8% | ✅ Hardware (Rigetti, IonQ, IBM) |
| QFT-space | 6 | 16 | 1,252 | ~0.15% | ✅ Simulator, ❌ Hardware |
| Ripple-carry | 7 | 23 | 7,040 | ~0% | Simulator only |

**Hardware fidelity math:** `0.995^CX_count`
- 4-bit: `0.995^716 ≈ 2.8%` → recoverable
- 6-bit: `0.995^1252 ≈ 0.15%` → buried in noise
- Need ≤ ~500 CX to have a fighting chance on 6-bit

---

## Papers to Read

| Paper | Link | Key Finding |
|---|---|---|
| Roetteler et al. 2017 | https://arxiv.org/abs/1905.09084 | Semiclassical QFT with qubit recycling — reduces period register from L qubits to **1 qubit** via measure-and-feed-forward. Eliminates most entangling gates in QFT phase. Could give 50%+ CX reduction. |
| | https://arxiv.org/abs/1905.09749 | |
| Häner et al. 2020 | https://arxiv.org/pdf/2001.09580 | Windowed arithmetic + binary Euclidean algorithm for modular inversion. 119× T-count improvement for 256-bit curves. Windowing principle applicable at small scale. |
| Gidney blog | https://algassert.com/post/2500 | Analysis of why factoring 21 needs 2,405 entangling gates vs 21 for factoring 15. Shows problem-specific constant exploitation is key — specific multiplier constants (1, powers-of-2) can have zero gate cost. |
| | https://arxiv.org/pdf/2504.09595 | |
| | https://arxiv.org/pdf/2506.03318 | |
| | https://arxiv.org/abs/2505.15917 | |
| | https://inria.hal.science/hal-04848612v1/document | |
| | https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=11087664 | |
| | https://eprint.iacr.org/2025/1887.pdf | |
| Approximate QFT | https://arxiv.org/abs/1803.04933 | O(n log n) T-gates instead of O(n log² n) |
| Schoolbook mult | https://arxiv.org/abs/2410.00899 | n² + 4n + 3 Toffoli gates (vs 2n² standard); ~30% reduction at small sizes |
| Truncated mod-exp | https://arxiv.org/abs/2405.17021 | Can omit >50% of levels without losing factorization — continued fractions only needs approximate phase |

For each paper: also mine its **citations and cited-by** for additional tricks.

---

## Optimization Ideas — Ranked by NISQ Impact

### 🥇 Semiclassical / Approximate QFT
The biggest lever. Currently x1 and x2 are full QFT registers. Options:

1. **Semiclassical QFT (Kitaev):** Measure each qubit of x1/x2 one at a time, classically compute feed-forward phase corrections, apply to remaining qubits. Reduces the QFT to single-qubit rotations. Requires mid-circuit measurement + feed-forward — supported on IonQ Forte and IBM (dynamic circuits). Potential: eliminate all entangling gates in the QFT stage.

2. **Approximate QFT:** Drop small-angle rotations (< π/2^k for some k) from the QFT. Rotations smaller than hardware noise floor are meaningless anyway. Reduces CX depth with controllable accuracy loss.

### 🥈 Exploit Problem-Specific Constants
From the Gidney analysis: the constants `G_STEPS` and `NEGQ_STEPS` are fixed per curve. For 4-bit (n=7): `G_STEPS = [1, 2, 4]`, `NEGQ_STEPS = [1, 2, 4]`. Adding 1, 2, 4 mod 7 are cheap. For 6-bit (n=31): `G_STEPS = [1, 2, 4, 8, 16]`. These are all powers of 2 mod 31 — potentially exploitable with shift-based circuits instead of general modular adders.

### 🥉 Truncate VAR_LEN
Use fewer QPE register bits (e.g. VAR_LEN=4 instead of 5 for n=31), accept lower success probability per shot, compensate with more shots. Truncated modular exponentiation paper shows >50% levels can be dropped. For our case: each dropped VAR_LEN bit saves ~2 controlled additions = significant CX reduction.

### Other Ideas
- [ ] Regev-style algorithm adaptation for ECDLP
- [ ] Shot/depth tradeoff analysis: how many shots needed vs circuit depth?
- [ ] Neutral atom hardware (QuEra, Pasqal) — different fidelity profile, all-to-all connectivity
- [ ] Error mitigation: zero-noise extrapolation on top of existing circuit
- [ ] `a=0` exploitation: point doubling formula simplifies to `slope = 3x²/2y` (no `a` term) — saves gates in (x,y) based approaches (less relevant for group-index encoding)

---

## Hints from Competition Notes

- Current implementation is **far too large** even for a 3-bit key with the naive approach
- `a=0` for all competition curves — algebraic simplification opportunity
- Notebook uses non-zero `INITIAL_POINT` to avoid defining point-at-infinity — keep this trick
- Explore tradeoffs between **number of shots** vs circuit depth/width
- **Iterative or approximate QFT** if hardware supports mid-circuit measurement + feed-forward
- Investigate **Regev's factoring algorithm** — may generalize to ECDLP
- For papers: mine citations in both directions
- NISQ focus: T-depth reduction is **less important** than CX count / total depth

---

## Hardware Fidelity Reference

| Hardware | Per-CX fidelity | Max viable CX for 1% circuit fidelity |
|---|---|---|
| IBM superconducting | ~99.5% | ~200 |
| IonQ Forte-1 (trapped-ion) | ~99.58% | ~240 |
| Rigetti Ankaa-3 | ~99.5% | ~200 |

Formula: `circuit_fidelity = fidelity^CX_count`
For 1% fidelity on IBM: `0.995^N = 0.01` → `N ≈ 918`
For 5% fidelity on IBM: `0.995^N = 0.05` → `N ≈ 596`
