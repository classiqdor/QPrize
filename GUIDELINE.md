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
- After verifying an attempt works, **append** it to `attempts/registry.py` (never edit past entries)
- Never delete or modify old attempt files

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

## What NOT to do

- Do not hardcode `d` into circuit constants (circular — defeats the purpose of ECDLP)
- Do not use `p.d` in the oracle; only use `p.G`, `p.Q`, `p.n`, `p.p`, `p.a`, `p.b`
- Do not run `git push` without pulling first
- Do not edit past entries in `registry.py` or `log.txt`
- Do not add `Co-Authored-By` to commit messages
- Do not use the full venv path (e.g. `/path/to/venv/bin/python`); activate the venv first
