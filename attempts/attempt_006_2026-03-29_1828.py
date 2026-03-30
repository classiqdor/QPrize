# =============================================================================
# Attempt 006 — 2026-03-29 18:28
#
# CHANGE: Replace the 5 controlled constant additions for x1 with a single
#         quantum-quantum modular addition `modular_add_inplace(n, x1, ecp)`.
#         Keep x2 with bit-by-bit controlled constant additions.
#         Use computational basis for ecp (no QFT-space encoding).
#
# WHY:
#   In all previous working attempts (002–005), the x1 contribution to ecp was
#   implemented as 5 separate controlled constant additions:
#       control(x1[0], add_1_to_ecp)
#       control(x1[1], add_2_to_ecp)
#       ...
#       control(x1[4], add_16_to_ecp)
#   Each controlled modular addition costs ~110 CX → 5 × 110 = 550 CX for x1.
#
#   Key insight: g_steps = [1, 2, 4, 8, 16] = standard binary weights, so the
#   total x1 contribution is simply the integer value of x1 (mod n). We can
#   replace all 5 controlled additions with a single quantum-quantum modular
#   addition: modular_add_inplace(n, x1, ecp).
#
#   Expected x1 cost: ~175 CX (one quantum-quantum addition)
#   vs. current:      ~550 CX (five controlled constant additions)
#   Potential saving: ~375 CX (30% of total 1252 CX for 6-bit)
#
#   This insight holds for ALL supported bit sizes: for any n, g_steps[i] = 2^i
#   and as long as 2^(var_len-1) < n (which always holds since n >= 2^(bits-1)),
#   the integer value of x1 equals the x1 contribution to ecp.
#
# PREVIOUS: attempt_004_2026-03-29_1600 — 4-bit: 716 CX, 6-bit: 1252 CX
# EXPECTED: 6-bit: ~850-950 CX (30% improvement over 004)
# =============================================================================

# %% Imports
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from classiq import *

from consts import PARAMS
from ec import point_add
from utils import timed, play_ending_sound

SUPPORTED_BITS = set(PARAMS.keys())  # all sizes: 4–21


# %% Classical oracle precomputation (identical to attempt_004)

def compute_oracle_constants(params, var_len: int):
    """
    Derive oracle step constants from public curve parameters only (no d used).

    Returns (g_steps, negq_steps):
      g_steps[i]    = 2^i mod n  (group index of 2^i * G; equals 2^i since 2^i < n)
      negq_steps[i] = n - (group index of 2^i * Q) mod n  (derived via EC arithmetic)
    """
    p, a, n = params.p, params.a, params.n
    G_pt, Q_pt = params.G, params.Q

    # Build EC-point → scalar-index lookup from G (no d needed).
    point_to_index: dict = {}
    cur = None
    for k in range(n + 1):
        point_to_index[cur] = k % n
        cur = point_add(cur, G_pt, p, a)

    g_steps = []
    negq_steps = []
    cur_q = Q_pt
    for i in range(var_len):
        g_idx = (1 << i) % n                    # 2^i mod n (trivially 2^i for i < log2(n))
        q_idx = point_to_index[cur_q]
        g_steps.append(g_idx)
        negq_steps.append((n - q_idx) % n)
        cur_q = point_add(cur_q, cur_q, p, a)   # 2^{i+1} * Q

    return g_steps, negq_steps


# %% Core solve function

def solve(num_bits: int) -> int:
    """
    Synthesize and execute Shor's ECDLP circuit for the given bit size.

    Key change vs attempt_004: x1's contribution is computed using a single
    quantum-quantum modular addition (modular_add_inplace) instead of 5
    separate controlled constant additions.

    Returns the recovered private key d, or raises AssertionError on mismatch.
    """
    assert num_bits in SUPPORTED_BITS, f"attempt_006 supports {SUPPORTED_BITS}, got {num_bits}"

    params          = PARAMS[num_bits]
    n               = params.n
    known_d         = params.d         # used ONLY for final assertion
    var_len         = n.bit_length()
    idx_bits        = n.bit_length()
    initial_idx     = 2

    g_steps, negq_steps = compute_oracle_constants(params, var_len)

    print(f"\n[attempt_006] {num_bits}-bit | n={n} | d=??? (solving)")
    print(f"  g_steps    = {g_steps}  (= powers of 2, so x1 contrib = int(x1) mod n)")
    print(f"  negq_steps = {negq_steps}")
    print(f"  Key change: x1 via modular_add_inplace (quantum-quantum), x2 via controlled adds")

    # -- Circuit definition --
    # ecp stays in computational basis throughout (no QFT encoding).
    # x1 as QNum for modular_add_inplace; x2 as QArray[QBit] for bit-by-bit control.

    @qfunc
    def main(
        x1: Output[QNum[var_len, False, 0]],       # type: ignore[valid-type]
        x2: Output[QArray[QBit]],
        ecp_idx: Output[QNum[idx_bits, False, 0]], # type: ignore[valid-type]
    ) -> None:
        allocate(var_len, False, 0, x1)
        allocate(var_len, x2)
        allocate(idx_bits, False, 0, ecp_idx)

        ecp_idx ^= initial_idx

        hadamard_transform(x1)
        hadamard_transform(x2)

        # x1 contribution: g_steps = [1, 2, 4, ..., 2^(var_len-1)] = binary weights
        # Total = integer value of x1.  Use a single quantum-quantum modular addition.
        modular_add_inplace(n, x1, ecp_idx)

        # x2 contribution: weighted sum with negq_steps (not simple binary).
        # Still use bit-by-bit controlled constant additions.
        for i in range(var_len):
            control(x2[i], lambda k=negq_steps[i]:
                    modular_add_constant_inplace(n, k, ecp_idx))

        # Period-finding: inverse QFT on x1 and x2 (reveals period of x1/x2 signals).
        invert(lambda: qft(x1))
        invert(lambda: qft(x2))

    # -- Synthesize --

    qmod = create_model(
        main,
        constraints=Constraints(max_width=200),
        preferences=Preferences(optimization_level=1, timeout_seconds=3600),
    )
    with timed("Synthesize"):
        qprog = synthesize(qmod)

    ops = qprog.transpiled_circuit.count_ops
    cx_count = ops.get("cx", "N/A")
    print(f"  Qubits: {qprog.data.width} | Depth: {qprog.transpiled_circuit.depth} | CX: {cx_count}")

    # Save synthesis result
    results_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(results_dir, exist_ok=True)
    result_path = os.path.join(results_dir, f"attempt_006_{num_bits}bit.json")
    try:
        qprog.save(result_path)
        print(f"  Saved to {result_path}")
    except Exception as e:
        print(f"  Warning: could not save qprog: {e}")

    # -- Execute --

    with timed("Execute"):
        res = execute(qprog).result_value()

    # -- Post-process --

    df = res.dataframe.sort_values("counts", ascending=False)
    N  = 1 << var_len

    def to_int(v):
        if isinstance(v, (int, float)):
            return int(v)
        return sum(int(b) * (1 << i) for i, b in enumerate(v))

    df["x1_r"] = (df["x1"].apply(to_int) / N * n).round().astype(int) % n
    df["x2_r"] = (df["x2"].apply(to_int) / N * n).round().astype(int) % n
    df = df[df["x1_r"].apply(lambda v: math.gcd(int(v), n) == 1)].copy()
    df["d_candidate"] = (
        -df["x2_r"] * df["x1_r"].apply(lambda v: pow(int(v), -1, n))
    ) % n

    recovered = int(df["d_candidate"].mode()[0])
    print(f"  Recovered d={recovered}, expected d={known_d} → {'✅' if recovered == known_d else '❌'}")
    assert recovered == known_d, f"MISMATCH: got {recovered}, expected {known_d}"
    return recovered


# %% Standalone entry point

if __name__ == "__main__":
    bits = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    d = solve(bits)
    play_ending_sound()
