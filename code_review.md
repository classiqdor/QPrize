# Mathematical Code Review: `attempt_002B_2026-03-29_1235.py`

**Verdict: APPROVED** with one documentation flag (no code bugs found)

---

## Summary

All five mathematical properties under review are correct. The circuit oracle, post-processing formula, degeneracy handling, and INITIAL_IDX treatment are all sound. One issue is noted in the companion test file `test_postprocessing.py`, which does not faithfully validate the formula used in attempt_002B — though both are equivalent by a register relabeling.

---

## 1. Correctness of the Group-Index Encoding Oracle

**CORRECT.**

The oracle builds:

```python
neg_q_step  = (generator_order - d) % generator_order          # = n - d
g_steps     = [(1 << i) % n for i in range(var_len)]           # = [2^0, 2^1, ..., 2^(k-1)] mod n
negq_steps  = [(neg_q_step * (1 << i)) % n for i in range(var_len)]
```

Then for each bit `x1[i]` it conditionally adds `g_steps[i]` to `ecp_idx` (mod n), and similarly for `x2[i]`.

Because `g_steps[i] = 2^i mod n` and the sequential modular additions are associative mod n:

```
Σᵢ x1[i] · g_steps[i]  ≡  Σᵢ x1[i] · 2^i  ≡  x1_value  (mod n)
Σᵢ x2[i] · negq_steps[i]  ≡  (n−d) · x2_value  (mod n)
```

Both identities were verified exhaustively for all x1, x2 ∈ [0, N) for n=7 and n=31.

The oracle therefore implements exactly:

```
ecp_idx = INITIAL_IDX + x1_value + (n−d) · x2_value   (mod n)
```

which is the intended group-index encoding: index `ecp_idx` denotes the EC group element `ecp_idx · G`. Adding 1 to the index equals adding G; adding (n−d) equals adding −d·G = −Q.

---

## 2. Correctness of the Post-Processing Formula `d = −x2_r · x1_r⁻¹ mod n`

**CORRECT.**

**Derivation.** After the oracle, the state is:

```
(1/N) Σ_{x1,x2} |x1⟩|x2⟩|INITIAL_IDX + x1 + (n−d)·x2 mod n⟩
```

Measuring `ecp_idx = v` collapses the `(x1, x2)` subsystem onto the coset:

```
{ (x1, x2) : x1 + (n−d)·x2 ≡ C (mod n) }   where C = v − INITIAL_IDX
```

Substituting j = x2 gives x1 = C + d·j (mod n), so the coset has position-space lattice generator **(d, 1)**: as x2 increases by 1, x1 increases by d (mod n).

After applying inverse QFT independently to x1 and x2, the amplitude at frequency pair (m1, m2) is proportional to:

```
Σⱼ exp(−2πi · j · (m1·d + m2) / N)
```

This sum is large when `m1·d + m2 ≡ 0 (mod n)`. So QFT peaks satisfy:

```
m1 · d + m2 ≡ 0   (mod n)
```

The post-processing maps measured values to integer frequencies via `x1_r = round(m1_measured / N · n)` and `x2_r = round(m2_measured / N · n)`, so `x1_r ≈ m1` and `x2_r ≈ m2`. Rearranging the peak condition:

```
d ≡ −m2 · m1⁻¹ ≡ −x2_r · x1_r⁻¹   (mod n)
```

**Numerical verification (6-bit, n=31, d=18).** From direct simulation of the QFT output:

- Peak at (x1_m=30, x2_m=5) → x1_r=29, x2_r=5:  `−5 · 29⁻¹ ≡ −5·15 ≡ 18 (mod 31)` ✓
- Peak at (x1_m=5, x2_m=3) → x1_r=5, x2_r=3:  `−3 · 5⁻¹ ≡ −3·25 ≡ 18 (mod 31)` ✓

The GCD filter `gcd(x1_r, n) == 1` is correct: it ensures x1_r (≈ m1) is invertible mod n, which is required to solve for d. Since all test parameters have prime n, only x1_r=0 fails the filter, which is the trivial DC peak.

---

## 3. Handling of the 4-Bit Degeneracy (d = n−1 = 6, n = 7)

**HANDLED CORRECTLY — no special case needed.**

For n=7, d=6: `neg_q_step = 7 − 6 = 1`. This means both `g_steps` and `negq_steps` are identical (`[1, 2, 4]`), so the oracle becomes:

```
ecp_idx = INITIAL_IDX + x1_value + x2_value   (mod 7)
```

The QFT frequency condition becomes `m1·6 + m2 = 0 (mod 7)`, i.e., `m2 = −6·m1 = m1 (mod 7)` (since −6 ≡ 1 mod 7). Therefore **all valid peaks have x1_r = x2_r**. Substituting into the formula:

```
d = −x2_r · x1_r⁻¹ = −x1_r · x1_r⁻¹ = −1 ≡ 6   (mod 7)  ✓
```

This is a structural coincidence of d=n−1 (which makes neg_q_step=1 = the g coefficient), not a bug. The formula recovers the correct d=6 naturally, and no special handling is needed. The degeneracy reduces information per peak (all peaks are on the x1_r=x2_r diagonal) but does not break the algorithm.

---

## 4. INITIAL_IDX Usage

**CORRECT — shifts the oracle but not the period.**

`INITIAL_IDX = 2` is applied as `ecp_idx ^= INITIAL_IDX` before the Hadamard transforms on x1/x2 and before all controlled additions. Its effect is to shift every ecp value by 2:

```
ecp_idx(x1, x2) = 2 + x1_value + (n−d)·x2_value   (mod n)
```

This shift enters the amplitude of peak (m1, m2) only as a global phase `exp(−2πi·m1·2/N)`, which does not affect the measurement probabilities.

The period structure of the (x1, x2) state is determined entirely by (n−d) and n, independent of the constant offset. INITIAL_IDX does not shift the period. The QFT output frequencies satisfy the same condition `m1·d + m2 = 0 (mod n)` regardless of INITIAL_IDX.

The purpose of choosing INITIAL_IDX = 2 (nonzero) is to ensure ecp_idx starts away from 0, avoiding a trivial fixed point where the oracle acts as identity for all-zero inputs. It is cosmetic from a mathematical standpoint.

---

## 5. Circuit Formula

**CORRECT.**

The stated formula is:

```
ecp_idx = INITIAL_IDX + Σᵢ x1[i]·2ⁱ + Σᵢ x2[i]·(n−d)·2ⁱ   (mod n)
```

The code implements this via:

```python
ecp_idx ^= INITIAL_IDX
for i in range(var_len):
    control(x1[i], lambda k=g_steps[i]:
            modular_add_constant_inplace(n, k, ecp_idx))
for i in range(var_len):
    control(x2[i], lambda k=negq_steps[i]:
            modular_add_constant_inplace(n, k, ecp_idx))
```

where `g_steps[i] = 2^i mod n` and `negq_steps[i] = (n−d)·2^i mod n`. The sequential modular additions accumulate correctly because:

```
((...((A + k0) mod n + k1) mod n + ...) mod n) = (A + Σ kᵢ) mod n
```

The reduction of each coefficient mod n before addition is valid because modular arithmetic distributes: `Σᵢ x[i]·(cᵢ mod n) ≡ Σᵢ x[i]·cᵢ (mod n)`. For the tested cases, all `2^i < n` for i < var_len (verified: 2^(var_len−1) ≤ n−1 by definition of bit_length), so the reduction is trivially exact.

---

## Flags and Notes

### Flag: `test_postprocessing.py` does not validate `attempt_002B`'s formula

`qday-prize/solution/test_postprocessing.py` uses the formula `−x1_r · x2_r⁻¹` applied to synthetic data where `x1_r = −d · x2_r mod n`. This is internally self-consistent but corresponds to the **register-swapped** convention (x1 ↔ x2 compared to the circuit). For 6-bit real circuit peaks, `−x1_r · x2_r⁻¹` gives **d=19, not d=18** (wrong), while `−x2_r · x1_r⁻¹` gives d=18 (correct).

For 4-bit, the two formulas coincide because the degeneracy forces `x1_r = x2_r`, so the swap is invisible. This is why `test_postprocessing.py` passes all cases — the 4-bit case doesn't distinguish the formulas, and for 6-bit+ the synthetic data is crafted to match its own formula. The test provides false assurance for the 6-bit formula.

**This is a documentation/test-coverage issue, not a bug in the production code.** The `attempt_002B.py` formula is the correct one.

### Note: `var_len = n.bit_length()` is correct

For all test parameters, `n.bit_length()` gives the minimum number of bits to represent values 0..n−1, and `N = 2^var_len` satisfies `n ≤ N < 2n`. The approximation error in the QFT peak rounding (`round(m_measured / N · n)`) is bounded by 0.5, which is acceptable for recovering the integer frequency.

### Note: ecp_idx as output register

Measuring `ecp_idx` alongside `x1` and `x2` is correct. The inv-QFT operations on x1 and x2 act on disjoint qubits from ecp_idx, so the two commute. Measuring ecp_idx collapses the state onto a coset; the QFT-transformed (x1, x2) subspace then yields the Fourier peaks as analyzed.

---

## Conclusion

The mathematical implementation is correct on all five criteria. The post-processing formula `d = −x2_r · x1_r⁻¹ mod n` correctly derives from the period lattice structure, and the oracle correctly implements the group-index encoding. The only issue worth addressing is aligning `test_postprocessing.py` to validate the actual circuit formula with realistic synthetic data.
