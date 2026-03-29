# QPrize — PLAN.md

> **Multi-agent note:** Multiple Claude instances may be running in parallel on different machines, each committing and pushing to the same repo. Always `git pull --rebase` before `git push`. This file is the coordination point — update it when you complete a task or start a new one.

---

## Current Status (2026-03-26)

| Bits | Attempts | Best CX | Fidelity | Status |
|------|----------|---------|----------|--------|
| 4    | 002B, 003 | 716 CX  | ~2.8%    | ✅ Working (simulator + hardware) |
| 6    | 002B, 003 | 1,252 CX | ~0.15%  | ✅ Simulator only — too noisy for hardware |
| 7+   | —        | —       | —        | ❌ Not attempted |

**Target:** Break the largest ECC key possible. Need ≤ ~500 CX for 6-bit hardware viability.

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

### 🥇 Priority 1: Semiclassical QFT
- **Idea:** Measure each qubit of x1/x2 one at a time, classically compute feed-forward phase corrections. Eliminates all entangling gates in the QFT phase.
- **Impact:** Could eliminate 200-400 CX gates from the QFT portion.
- **Status:** No built-in in Classiq SDK (confirmed by searching Cadmium source). Must implement manually using `measure()` + classical feed-forward.
- **Hardware requirement:** Needs mid-circuit measurement + feed-forward. Supported on IonQ Forte-1, IBM (dynamic circuits).
- **Next step:** Prototype in attempt_004.

### 🥈 Priority 2: Approximate QFT
- **Idea:** Drop QFT rotation gates smaller than hardware noise floor (< π/2^k for hardware-appropriate k). Meaningless rotations get dropped for free.
- **Impact:** Reduces CX count in QFT with controllable accuracy loss. Potentially 30-50 CX saved.
- **Status:** No `approximation_degree` parameter in Classiq QFT (confirmed). Must manually reconstruct QFT with dropped rotations using `@qfunc` + `phase` gates.
- **Next step:** Implement after semiclassical QFT attempt.

### 🥉 Priority 3: Exploit Power-of-2 Constants
- **Idea:** For 6-bit (n=31), `G_STEPS = [1, 2, 4, 8, 16]` — all powers of 2. A controlled add of 2^k = bit shift, which may have much lower gate cost than general modular adder.
- **Relevant:** Gidney blog shows specific constants can have zero gate cost when circuit is designed around them.
- **Status:** Classiq SDK uses generic `modular_add_constant_inplace`. May need custom `@qfunc` decomposition.
- **Next step:** Check if Classiq has constant-specific adder synthesis, or implement bit-shift-based mod adder.

### Priority 4: Truncate VAR_LEN
- **Idea:** Use fewer QPE register bits (e.g. 4 instead of 5 for n=31). Each dropped bit saves 2 controlled additions. Accept lower success probability, compensate with more shots.
- **Impact:** Could halve CX count at cost of 2× more shots.
- **Risk:** Post-processing rounding gets less accurate with fewer bits.
- **Reference:** "Truncated modular exponentiation" paper — >50% levels can be dropped.
- **Status:** Easy to implement, try in attempt_005.

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
| 004 | — | Semiclassical QFT | — | — | Planned |

---

## Infrastructure Done

- `consts.py` — all competition curves, bits 4–21
- `attempts/registry.py` — append-only history of working attempts
- `test_attempts.py` — runs latest registered attempt for each bit size
- `test_validation.py` — algebraic + quantum + code-review validation suite
- `utils.py` — `timed()` context manager, `play_ending_sound()` (Linux + Mac)
- `research.md` — papers, optimization ideas, hardware fidelity reference
- GitHub: https://github.com/classiqdor/QPrize
