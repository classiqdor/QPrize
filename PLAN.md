# QPrize — PLAN.md

> **Multi-agent note:** Multiple Claude instances may be running in parallel on different machines, each committing and pushing to the same repo. Always `git pull --rebase` before `git push`. This file is the coordination point — update it when you complete a task or start a new one.

---

## Current Status (2026-03-29)

| Bits | Attempts | Best CX | Fidelity | Status |
|------|----------|---------|----------|--------|
| 4    | 002B, 003, 004 | 716 CX | ~2.8% | ✅ Working (simulator + hardware) |
| 6    | 002B, 003, 004 | 1,252 CX | ~0.15% | ✅ Simulator only — too noisy for hardware |
| 7+   | —        | —       | —        | ❌ Not attempted |

**Target:** Break the largest ECC key possible. Need ≤ ~500 CX for 6-bit hardware viability.

### ⚠️ Critical fix in attempt_004: attempts 002–003 were using d directly in the oracle
Both previous approaches encoded `neg_q_step = (n-d) % n` — knowing d before solving. See below for two different fix approaches.

---

## A) Verification: Are We Solving the Right Problem?

### What we've done
- **Mathematical code review** (`code_review.md`): Formally verified 5 properties of attempt_002B:
  - Oracle formula correct: `ecp_idx = INITIAL_IDX + x1 + (n−d)·x2 (mod n)` ✅
  - Post-processing formula correct: `d = −x2_r · x1_r⁻¹ mod n` ✅
  - 4-bit degeneracy (d=n-1) handled correctly by the formula ✅
  - INITIAL_IDX does not affect recovered d (only global phase) ✅
  - Modular additions accumulate correctly ✅

- **Test suite** (`test_validation.py`):
  - `[algebraic]` tests (instant, pure math):
    - `test_algebraic_constants` — G_STEPS and NEGQ_STEPS correct for bits 4, 6, 7
    - `test_algebraic_postprocessing` — formula `d = −x2_r·x1_r⁻¹` correct for all valid pairs
    - `test_algebraic_4bit_degeneracy` — confirms x1_r = x2_r for d=n-1
  - `[quantum]` tests (require circuit execution, ~60s):
    - `test_quantum_recovers_correct_d` — baseline: correct params → correct d
    - `test_quantum_null_wrong_d` — **null test**: wrong d → wrong answer (proves d is encoded)
    - `test_quantum_initial_idx_invariance` — idx=2 and idx=4 give same d
    - `test_quantum_distribution_structure` — valid pairs enriched vs random baseline
  - `[review]` test: `test_code_review_approved` — checks code_review.md for APPROVED verdict

### Known issue to fix
- `test_algebraic_postprocessing` uses the register-swapped formula (`−x1_r·x2_r⁻¹`) with synthetic data that matches that convention. For 6-bit real circuit output, this gives wrong results. Fix: update synthetic data to use real circuit convention (`−x2_r·x1_r⁻¹`).

### Still TODO for verification
- [ ] Run `pytest test_validation.py -v -k algebraic` — instant, should pass
- [ ] Run `pytest test_validation.py -v -k quantum` — ~60s, the real confidence check
- [ ] Fix `test_algebraic_postprocessing` to use correct formula convention
- [ ] Add a 6-bit quantum validation test (currently all quantum tests are 4-bit)

---

## B) Improving the Solution — Optimization Roadmap

**Goal:** Get 6-bit to ≤ 500 CX (from 1,252). Stretch: reach 7-bit.

### ~~Priority 1: Semiclassical QFT~~ ❌ Not Worth It (4% savings)
- **Result:** H + inv_QFT(x1, x2) = only **52 CX** out of 1,252 total (4%). Bottleneck is controlled modular additions (~120 CX each × 10 = ~1,200 CX).
- **Lesson:** Semiclassical QFT only helps when QFT dominates. In our circuit, it doesn't.

### ~~Priority 1: Exploit Power-of-2 G_STEPS Constants~~ ❌ Already Exploited
- **Result:** Classiq synthesizer already exploits trailing zeros: CX = 122 - 6×(trailing_zeros(k)) for mod-31 QFT-space add. Savings are modest (≤24 CX per addition).
- **Also measured:** mod 32 vs mod 31: only **8 CX less per addition**. Mersenne trick saves little.
- **Root cause:** Per-addition cost scales as ~4n² CX (Beauregard-style QFT comparison oracle is O(n²)). Constant structure cannot overcome this.

### 🥇 Priority 1: Quantinuum H-Series Hardware for 7-bit
- **Idea:** Quantinuum H2 has ~99.9% 2Q fidelity. For 7-bit (3212 CX): 0.999^3212 ≈ 4.1% fidelity. Much better than IBM (0.15% for 6-bit). Could get correct answers.
- **Impact:** Demonstrate 7-bit ECDLP (d=56) on hardware — likely the competition goal.
- **Status:** Need to check Classiq backend list and obtain Quantinuum access.
- **Next step:** Check available backends via Classiq SDK, request access.

### 🥈 Priority 2: Alternative Algorithm with Fewer Oracle Calls
- **Idea:** Windowed exponentiation or Regev-style multi-dimensional period finding to reduce number of controlled additions (currently 2×var_len = 10).
- **Status:** Needs research. Windowed approach: group var_len bits into windows of w, reduces additions from 2n to 2n/w at cost of 2^w different lookup values per window.
- **Next step:** Research Regev (2023) and windowed approach applicability to ECDLP.

### ~~Priority 2: Approximate QFT~~ Low Priority
- **Impact:** QFT only contributes ~104 CX (8% of total). Not the bottleneck.

### ~~Priority 4: Truncate VAR_LEN~~ ❌ Does Not Work
- **Result:** var_len=4 → top candidate d=0 (❌); var_len=3 → top candidate d=30 (❌). Both fail.
- **Why:** n=31 requires N=2^var_len ≥ n to resolve QFT peaks. With N=16 < 31, peaks from different m fold together — the signal is destroyed, not reduced.
- **Lesson:** For Shor's period finding, you need N ≥ n. Full var_len is mandatory.
- **Tested in:** attempt_005 (6-bit, n=31)

### Priority 5: Regev's Algorithm
- **Idea:** Regev (2023) improved Shor's factoring algorithm; may generalize to ECDLP.
- **Status:** Needs careful reading and implementation. Not yet investigated.

### Priority 6: Neutral Atom Hardware
- **Idea:** QuEra, Pasqal — different fidelity profile, all-to-all connectivity, potentially better for our circuit structure.
- **Status:** Check if Classiq supports these backends.

---

## Attempt History

| Attempt | Date | Key change | 4-bit CX | 6-bit CX | Status |
|---------|------|-----------|---------|---------|--------|
| 001 | 2026-03-29 12:12 | Naive (x,y) coordinates | — | — | Obsolete |
| 002 | 2026-03-29 12:30 | Group-index encoding, standalone | 716 | 1,252 | Baseline |
| 002B | 2026-03-29 12:35 | Refactored to export solve() | 716 | 1,252 | ✅ Working |
| 003 | 2026-03-29 14:20 | optimization_level=1 | 716 | 1,252 | No improvement |
| 004 (1507) | 2026-03-29 15:07 | **Quantum EC arithmetic** — EllipticCurvePoint (x,y) QStruct, quantum ec_point_add | TBD | TBD | Unverified — correct but expensive |
| 004 (1600) | 2026-03-29 16:00 | **Classical enumeration** — derive negq_steps from Q via EC point lookup table, same scalar oracle | 716 | 1,252 | ✅ Verified (d=6, d=18, d=56) |
| 005 | 2026-03-29 | **Truncated var_len** — var_len=4 (1022 CX) and var_len=3 (778 CX) for 6-bit | — | 1022/778 | ❌ Fails — N must be ≥ n for QFT peaks to resolve |
| 006 (ec_coords) | 2026-03-29 | **Genuine ECDLP** — EC coordinate register (x,y)∈F_p, Roetteler 2017, d never used | ~130k CX | — | Synthesized (28q, 129938 CX), execution timed out |
| 004B | 2026-03-29 19:00 | Re-verified 004-1600 with cleaner run | 716 | 1,252 | ✅ (d=6, d=18) |
| 006B | 2026-03-29 19:00 | (pending) | — | — | Not yet run |
| 007 | 2026-03-29 18:40 | **Scalable coordinate oracle** — Kaliski modular inverse (QNum[…]() vars), Roetteler 2017 | TBD | TBD | Written, not yet run |
| 008 | 2026-03-29 18:59 | **Scalable coordinate oracle** — same as 007, named QNum("name",n) vars for better synthesis output | TBD | TBD | Written, not yet run |

### ⚠️ Correctness: attempts 002B–005 are NOT genuine ECDLP

Scalar-index encoding (002B, 003, 004-1600, 005) implicitly computes d before running
the quantum circuit: `negq_steps[i] = (n − point_to_index[2^i·Q]) % n` looks up Q's
scalar index via a brute-force enumeration of the EC group — that IS the discrete log.
The quantum circuit then does integer arithmetic in Z_n (DLP in Z_n, trivially easy).

The genuine ECDLP approach (004-1507, 006, 007, 008) uses EC coordinates (x,y) in F_p for the
oracle register, and derives neg_q_powers by EC point doubling of Q without knowing d.
See GUIDELINE.md "Genuine ECDLP vs. the Scalar-Encoding Flaw".

### Two approaches to fixing the oracle (both correct, different cost):

**004-1507 / 006 / 007 / 008 (quantum EC arithmetic):**
- Oracle register holds (x, y) coordinates mod p
- `ec_scalar_mult_add` does controlled quantum EC point addition
- 004-1507/006: lookup-table modular inverse (feasible for small p, not scalable)
- 007/008: Kaliski modular inverse (O(p_bits²) gates, scalable to any key size)
- Does not assume knowledge of d at any point

**004-1600 / 004B (classical enumeration + scalar oracle) — NOT scalable:**
- Classically enumerates all n EC group elements to build point→index table
- Uses this to find index of 2^i*Q without knowing d
- Same cheap scalar oracle (modular additions mod n) as 002B/003
- Feasible for competition sizes (n ≤ ~50000), infeasible for cryptographic sizes

---

## Infrastructure Done

- `consts.py` — all competition curves, bits 4–21
- `attempts/registry.py` — append-only history of working attempts
- `test_attempts.py` — runs latest registered attempt for each bit size
- `test_validation.py` — algebraic + quantum + code-review validation suite
- `utils.py` — `timed()` context manager, `play_ending_sound()` (Linux + Mac)
- `research.md` — papers, optimization ideas, hardware fidelity reference
- GitHub: https://github.com/classiqdor/QPrize
