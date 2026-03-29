# GUIDELINE.md

Working conventions for the QPrize project. Both humans and Claude instances should follow these when contributing.

---

## Attempt Files

- Every attempt lives in `attempts/attempt_NNN[letter]_YYYY-MM-DD_HHMM.py`
  - `NNN` = zero-padded attempt number; letter suffix (B, C, ...) = refinement of same idea
  - `YYYY-MM-DD_HHMM` = actual creation date and time (use `date +%Y-%m-%d_%H%M`)
  - Example: `attempt_004_2026-03-29_1507.py`
- Every attempt file must:
  - Have a header comment explaining **what changed** and **why** (vs previous attempt)
  - Export `solve(num_bits: int) -> int` that synthesizes + executes + returns recovered d
  - Call `play_ending_sound()` when finished
  - Use `timed()` context managers around slow steps
  - Save the synthesis result to `attempts/results/attempt_NNN_<bits>bit.json` (create dir if needed)
- After verifying an attempt works, **append** it to `attempts/registry.py` (never edit past entries)
- Add a row to `attempts/RESULTS.md` for each synthesis run with: attempt name, bits, qubit width, circuit depth, CX count, success (✅/❌)
- Never delete or modify old attempt files

### Results table (`attempts/RESULTS.md`)

Append one row per synthesis run (not per attempt file). Columns:

| Attempt | Bits | Width | Depth | CX | Success |
|---------|------|-------|-------|----|---------|
| attempt_004_2026-03-29_1507 | 4 | 11 | ... | 716 | ✅ |

- **Width** = number of qubits (from `GeneratedCircuit.data.width`)
- **Depth** = circuit depth (from `GeneratedCircuit.data.depth`)
- **CX** = two-qubit gate count (from `GeneratedCircuit.data.transpiled_circuit.count_ops["cx"]` or equivalent)
- **Success** = ✅ if `solve()` returned the correct `d`, ❌ otherwise

The JSON result file (saved to `attempts/results/`) should include the same fields plus the raw `GeneratedCircuit` metadata. Use `GeneratedCircuit.save(path)` or serialize manually.

---

## PLAN.md

`PLAN.md` is the **strategic document**. Keep it up to date:
- When a task is completed, move it from "TODO" to "done" or update the attempt history table
- When a new idea is discovered (from papers, experiments, failures), add it under the appropriate priority section
- Note qubit/CX counts and status (Simulator / Hardware / Failed) for each attempt
- The multi-agent coordination note at the top should remain; multiple Claude instances read it

---

## Work Log

All session activity is documented in `worklog/`. Each session creates one file:
- Filename: `worklog/YYYY-MM-DD_HHMM_[who].md` (e.g. `worklog/2026-03-29_1200_dor.md`)
- Format: bullet list of what was done, ideas explored, decisions made, failed attempts, and open questions
- **A new session should read the latest worklog file first** to pick up where the previous session left off
- Also append a one-liner summary to `log.txt` in the root (append-only, never edit past entries)

Template for a worklog entry:
```markdown
# Session YYYY-MM-DD HH:MM — [who]

## Done
- ...

## Failed / Abandoned
- ...

## Open questions / Next steps
- ...
```

---

## Code Structure

### Root folder — keep organized
- `consts.py` — curve parameters only, no circuit code
- `utils.py` — shared utilities (`timed`, `play_ending_sound`)
- `ecc.py` — classical EC arithmetic helpers (for testing/reference)
- `attempts/` — attempt files + registry
- `worklog/` — session logs
- `PLAN.md` — strategic plan and attempt history
- `GUIDELINE.md` — this file
- `research.md` — paper notes and optimization ideas
- `test_*.py` — pytest test files
- `code_review.md` — latest agent code review output

Do not clutter the root with scratch files, temp outputs, or one-off scripts.

### Attempt file structure
```python
# attempt_NNN — YYYY-MM-DD HH:MM
# CHANGE: ...
# WHY: ...
# (optional: RESULT: ...)

import ...
from consts import PARAMS
from utils import timed, play_ending_sound

def solve(num_bits: int) -> int:
    ...
    play_ending_sound()
    return d

if __name__ == "__main__":
    # Quick smoke test
    result = solve(4)
    print(result)
```

### Classiq conventions
- The Classiq entry-point `@qfunc` must be named `main`
- Define `main` inside `solve()` so it captures local constants via closure
- Use `@qperm` for reversible helpers (no mid-circuit measurement), `@qfunc` for the top-level
- Lambda capture in loops: use default argument `lambda x=val: f(x)` not bare `lambda: f(val)` where `val` changes in the loop
- `allocate(size, signed, fraction_digits, reg)` — use `fraction_digits=size` for fractional QNum (values in [0,1)), use `fraction_digits=0` for integer QNum
- `free(reg)` is required for any register allocated inside a `@qperm` but not returned

### ⚡ Strong suggestion: split `main` into three named sub-functions

The core bottleneck is the group addition oracle, not the Hadamard or QFT layers. To keep
focus there and avoid conflating unrelated parts of the circuit, split `main` into three
clearly named helpers and have `main` call them in order:

```python
@qfunc
def prepare_superposition(x1: Output[QArray[QBit]], x2: Output[QArray[QBit]]) -> None:
    """Allocate and Hadamard the two QPE registers."""
    allocate(var_len, x1)
    allocate(var_len, x2)
    hadamard_transform(x1)
    hadamard_transform(x2)

@qfunc   # (or @qperm if reversible)
def group_add_oracle(
    x1: QArray[QBit],
    x2: QArray[QBit],
    ecp: Output[...],
) -> None:
    """The group addition oracle — ecp = P0 + x1*G - x2*Q. This is the hard part."""
    ...

@qfunc
def extract_phase(x1: QArray[QBit], x2: QArray[QBit]) -> None:
    """Inverse QFT to extract the period."""
    invert(lambda: qft(x1))
    invert(lambda: qft(x2))

@qfunc
def main(x1: Output[QArray[QBit]], x2: Output[QArray[QBit]], ecp: Output[...]) -> None:
    prepare_superposition(x1, x2)
    group_add_oracle(x1, x2, ecp)
    extract_phase(x1, x2)
```

**Why:** Every attempt optimizes `group_add_oracle`. Keeping it isolated makes it easy to
swap implementations, compare CX counts, and avoids accidentally touching the Hadamard or
QFT layers when experimenting with the oracle.

### Post-processing convention
The oracle is: `ecp = P0 + x1*G - x2*Q`

Peak condition after inverse QFT: `m1*d + m2 ≡ 0 (mod n)`

Standard post-processing (attempt_004+):
```python
x1_r = round(x1_measured * n) % n   # frequency m1
x2_r = round(x2_measured * n) % n   # frequency m2
# filter: gcd(x1_r, n) == 1
d = (-x2_r * pow(x1_r, -1, n)) % n
```

**Note:** The reference Classiq notebook uses `d = -x1_r * x2_r^{-1}` which is only correct for their degenerate test case (d=n-1). For the competition curves (d≠n-1), use the formula above.

---

## Git Workflow

- Always `git pull --rebase` before `git push`
- Multiple Claude instances may be running in parallel on different machines; git is the coordination mechanism
- Check `log.txt` and recent `worklog/` files after pulling to catch up on parallel work
- Commit message format: short imperative, no "Co-Authored-By" trailers

---

## Genuine ECDLP vs. the Scalar-Encoding Flaw

### The flaw (attempts 002B, 003, 004-1600, 005)

These attempts use **scalar-index encoding**: EC group elements are stored as integers
in Z_n (the scalar index k, where the element equals k·G). The oracle then computes:

    negq_steps[i] = (n − scalar_index(2^i · Q)) % n

But `scalar_index(Q) = d` — the secret itself. Even deriving it "indirectly" via a
brute-force point_to_index enumeration still means d is solved classically before the
quantum circuit runs. The quantum step is then redundant.

The quantum circuit computes `x1 − x2·d  (mod n)` — arithmetic in Z_n, not EC arithmetic.

### The genuine approach (attempt 004-1507, 006+)

The oracle register must hold **EC coordinates** `(x, y) ∈ F_p × F_p`. Precomputed
classical constants must be EC points derivable from G and Q *without knowing d*:

    g_powers[i]      = 2^i · G     (doublings of G — uses only G)
    neg_q_powers[i]  = −(2^i · Q)  (doublings of Q, negate y — uses only Q as a point)

The quantum circuit applies controlled **EC point additions** (slope formula mod p).
`d` is never used anywhere in circuit construction.

### Rule

**The oracle must never use `params.d`.** Allowed inputs: `params.G`, `params.Q`,
`params.p`, `params.n`, `params.a`, `params.b`.

If you find yourself computing `(n − d) % n`, looking up d in a lookup table, or using
`point_to_index` to convert Q to a scalar, the attempt is NOT genuine ECDLP.

---

## What NOT to do

- Do not hardcode `d` into circuit constants (circular — defeats the purpose of ECDLP)
- Do not use `params.d` in the oracle; only use `params.G`, `params.Q`, `params.n`, `params.p`, `params.a`, `params.b`
- Do not use scalar-index encoding for the oracle register (see "Genuine ECDLP" section above)
- Do not run `git push` without pulling first
- Do not edit past entries in `registry.py` or `log.txt`
- Do not add `Co-Authored-By` to commit messages
- Do not use the full venv path (e.g. `/path/to/venv/bin/python`); activate the venv first
