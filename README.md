# QPrize — Shor's ECDLP on Quantum Hardware

Attempt to break the largest possible ECC key using Shor's algorithm on real quantum hardware, as part of the [QDay Prize](https://www.qdayprize.org) competition (deadline: April 5, 2026).

All competition curves use `y² = x³ + 7 (mod p)` — the same form as Bitcoin's secp256k1.

---

## Structure

### `consts.py`
All competition curve parameters for bit sizes 4–21, parsed from [curves.txt](https://www.qdayprize.org/curves.txt).

```python
from consts import PARAMS
params = PARAMS[6]   # 6-bit curve
print(params.p, params.n, params.G, params.Q, params.d)
```

Each `Parameters` object holds: `bits`, `p`, `order_E`, `n`, `h`, `G`, `Q`, `d`, `a=0`, `b=7`.

---

### `attempts/`
Each attempt is a self-contained Python file named `attempt_NNN[letter]_YYYY-MM-DD_HHMM.py`.

Every attempt exports a `solve(num_bits: int) -> int` function that synthesizes and executes the circuit, and returns the recovered private key `d`.

The header comment of each file explains what changed from the previous attempt and why.

**Naming convention:**
- `attempt_002` → the attempt as originally written
- `attempt_002B` → a revised version of the same attempt (refactored, not a new idea)
- `attempt_003` → a new optimization idea

**Current attempts:**

| File | Bit sizes | Key idea |
|---|---|---|
| `attempt_001` | 4 | Naive (x,y) coordinate representation — obsolete |
| `attempt_002` | 4, 6 | Group-index encoding baseline (standalone script) |
| `attempt_002B` | 4, 6 | Same, refactored to export `solve()` |
| `attempt_003` | 4, 6 | `optimization_level=1` — let Classiq's synthesizer optimize |

---

### `attempts/registry.py`
Maps each bit size to its list of working attempts (oldest first). The last entry per bit size is what the test suite runs. **Append-only** — never remove entries.

```python
LATEST = {
    4: [
        {"attempt": "attempt_002B_2026-03-29_1235", "expected_seconds": 15},
        {"attempt": "attempt_003_2026-03-29_1420", "expected_seconds": 60},
    ],
    ...
}
```

---

### `test_attempts.py`
pytest-based test suite. Runs the latest registered attempt for each bit size and asserts the recovered `d` matches `consts.PARAMS[bits].d`.

```bash
pytest test_attempts.py -v          # all bit sizes
pytest test_attempts.py -v -k bits4 # just 4-bit (~20s)
pytest test_attempts.py -v -k bits6 # just 6-bit (~120s)
```

`pytest.ini` sets `--durations=0` automatically so timing is always shown.

---

### `research.md`
Paper list, optimization ideas ranked by NISQ impact, hardware fidelity reference, and notes on what the colleague's prior work already covered.

---

### `utils.py`
Shared utilities:
- `timed(label)` — context manager that prints elapsed time every 10s and total on exit
- `play_ending_sound()` — plays a completion sound when a script finishes

---

## Setup

```fish
source /home/dor/Sources/Classiq/claude_repos/venv/bin/activate.fish
```

See `CLAUDE.md` for full setup instructions.

---

## Algorithm

We use **group-index encoding**: instead of storing EC points as `(x, y)` coordinate pairs (requiring quantum modular inversion), points are stored as their scalar index `k` meaning `k·G`. The full oracle reduces to controlled modular additions of precomputed constants — dramatically cheaper.

**Circuit formula:**
```
ecp = INITIAL_IDX + Σᵢ x1[i]·2ⁱ + Σᵢ x2[i]·(n−d)·2ⁱ  (mod n)
```

Two variants:
- **Ripple-carry** (`modular_add_constant_inplace`) — fewer gates for small n, proven on hardware for 4-bit
- **QFT-space** (`modular_add_qft_space`) — 57% fewer CX gates for 6-bit+

**Current best results:**

| Bits | Qubits | CX gates | Status |
|---|---|---|---|
| 4 | 11 | 716 | ✅ Simulator + hardware (colleague) |
| 6 | 16 | 1,252 | ✅ Simulator only |
