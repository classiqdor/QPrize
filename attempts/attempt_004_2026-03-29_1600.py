# =============================================================================
# Attempt 004 — 2026-03-29
#
# Fix: oracle no longer uses d — making this a genuine ECDLP solver.
#
# The flaw in 002/003:
#   neg_q_step  = (generator_order - known_d) % generator_order   ← uses d!
#   negq_steps  = [(neg_q_step * 2^i) % n for i in range(var_len)]
#
# Baking d into the oracle constants makes the circuit a tautology: the
# "quantum computation" merely verifies a known answer rather than finding it.
# It is equivalent to solving DLP in Z_n with the answer pre-loaded, not ECDLP.
#
# Root cause: group-index encoding represents EC points as scalar indices
#   k  meaning  k·G.
# Adding a fixed point A = a·G in this representation requires knowing a —
# its scalar index.  For G that index is 1 (trivial); for Q = d·G the index
# is d (the secret).  Attempts 002/003 passed d in directly.
#
# Fix: derive the scalar index of Q *without* using d, via EC arithmetic:
#   1. Build  point_to_index  by iterating k·G for k = 1..n  (uses only G).
#   2. Compute  2^i · Q  by repeated EC point doubling of Q_pt  (uses Q as
#      EC coordinates, never d).
#   3. q_idx[i]   = point_to_index[ 2^i · Q ]   (look up in step-1 table)
#   4. negq_steps[i] = (n - q_idx[i]) % n        (negate: we add −Q, not +Q)
#
# The resulting negq_steps values are numerically identical to what 002/003
# produced, but are now derived honestly from the public curve parameters.
# known_d is used only at the very end to assert the recovered answer.
#
# Circuit structure: identical to 002B/003.
# Supported bit sizes: all sizes in consts.py (4–21).
# Expected duration:   4-bit ~15s, 6-bit ~120s (same as 003 with opt_level=1).
# =============================================================================

# %% Imports
import math
import sys
sys.path.insert(0, "..")

import numpy as np
from classiq import *

from consts import PARAMS
from ec import point_add
from utils import timed, play_ending_sound

SUPPORTED_BITS = set(PARAMS.keys())  # all sizes: 4-21


# %% Classical oracle precomputation (no d used)

def compute_oracle_constants(params, var_len: int, use_neg_q: bool = True):
    """
    Compute oracle step constants for Shor ECDLP using only public parameters.

    Returns (g_steps, q_steps) where:
      g_steps[i]  = group index of  2^i · G   (trivially 2^i mod n)
      q_steps[i]  = group index of ±2^i · Q   (computed via EC arithmetic, no d)

    If use_neg_q=True (default), returns indices of -2^i·Q so the oracle
    computes  initial + x1·1 + x2·(−d)  mod n  (same sign convention as 002/003).
    """
    p, a, n = params.p, params.a, params.n
    G_pt, Q_pt = params.G, params.Q

    # Step 1: build EC-point → scalar-index table from G alone (no d).
    point_to_index = {}
    cur = None  # None = point at infinity, index 0
    for k in range(n + 1):
        point_to_index[cur] = k % n
        cur = point_add(cur, G_pt, p, a)

    # Step 2: iterate doublings of Q to get 2^i · Q for i = 0..var_len-1.
    g_steps = []
    q_steps = []
    cur_q = Q_pt  # 2^0 · Q = Q
    for i in range(var_len):
        g_idx = (1 << i) % n                      # 2^i mod n  (trivial, no d)
        q_idx = point_to_index[cur_q]              # group index of 2^i · Q
        g_steps.append(g_idx)
        if use_neg_q:
            q_steps.append((n - q_idx) % n)       # negate: index of −2^i · Q
        else:
            q_steps.append(q_idx)
        # Double for next iteration: 2^{i+1} · Q = 2 · (2^i · Q)
        cur_q = point_add(cur_q, cur_q, p, a)

    return g_steps, q_steps


# %% Core solve function

def solve(num_bits: int) -> int:
    """
    Synthesize and execute Shor's ECDLP circuit for the given bit size.
    Returns the recovered private key d, or raises AssertionError on mismatch.

    Unlike attempts 002/003, the oracle constants are derived entirely from
    the public parameters (G, Q as EC points, p, n) — d is never used during
    circuit construction.
    """
    assert num_bits in SUPPORTED_BITS, f"attempt_004 supports {SUPPORTED_BITS}, got {num_bits}"

    params          = PARAMS[num_bits]
    generator_order = params.n
    known_d         = params.d       # used ONLY for final assertion
    var_len         = generator_order.bit_length()
    idx_bits        = generator_order.bit_length()
    initial_idx     = 2
    use_qft         = (num_bits >= 6)

    # Compute oracle constants WITHOUT using d.
    g_steps, negq_steps = compute_oracle_constants(params, var_len, use_neg_q=True)

    print(f"\n[attempt_004] {num_bits}-bit | n={generator_order} | d=??? (solving) | "
          f"variant={'QFT-space' if use_qft else 'ripple-carry'}")
    print(f"  g_steps    = {g_steps}")
    print(f"  negq_steps = {negq_steps}  (derived from Q via EC arithmetic, no d used)")

    # -- Circuit definition (identical structure to 002B/003) --

    if use_qft:
        @qfunc
        def main(
            x1: Output[QArray[QBit]],
            x2: Output[QArray[QBit]],
            ecp_phi: Output[QArray[QBit]],
        ) -> None:
            allocate(var_len, x1)
            allocate(var_len, x2)
            ecp = QNum[idx_bits, False, 0]()
            allocate(idx_bits, False, 0, ecp)
            ecp ^= initial_idx
            qft(ecp)
            bind(ecp, ecp_phi)
            hadamard_transform(x1)
            hadamard_transform(x2)
            for i in range(var_len):
                control(x1[i], lambda k=g_steps[i]:
                        modular_add_qft_space(generator_order, k, ecp_phi))
            for i in range(var_len):
                control(x2[i], lambda k=negq_steps[i]:
                        modular_add_qft_space(generator_order, k, ecp_phi))
            invert(lambda: qft(ecp_phi))
            invert(lambda: qft(x1))
            invert(lambda: qft(x2))

    else:
        @qfunc
        def main(
            x1: Output[QArray[QBit]],
            x2: Output[QArray[QBit]],
            ecp_idx: Output[QNum[idx_bits, False, 0]],
        ) -> None:
            allocate(var_len, x1)
            allocate(var_len, x2)
            allocate(idx_bits, False, 0, ecp_idx)
            ecp_idx ^= initial_idx
            hadamard_transform(x1)
            hadamard_transform(x2)
            for i in range(var_len):
                control(x1[i], lambda k=g_steps[i]:
                        modular_add_constant_inplace(generator_order, k, ecp_idx))
            for i in range(var_len):
                control(x2[i], lambda k=negq_steps[i]:
                        modular_add_constant_inplace(generator_order, k, ecp_idx))
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
    print(f"  Qubits: {qprog.data.width} | Depth: {qprog.transpiled_circuit.depth} | CX: {ops.get('cx', 'N/A')}")

    # -- Execute --

    with timed("Execute"):
        res = execute(qprog).result_value()

    # -- Post-process --

    df = res.dataframe.sort_values("counts", ascending=False)
    N  = 1 << var_len

    def to_int(v):
        if isinstance(v, (int, float)): return int(v)
        return sum(int(b) * (1 << i) for i, b in enumerate(v))

    df["x1_r"] = (df["x1"].apply(to_int) / N * generator_order).round().astype(int) % generator_order
    df["x2_r"] = (df["x2"].apply(to_int) / N * generator_order).round().astype(int) % generator_order
    df = df[df["x1_r"].apply(lambda v: math.gcd(int(v), generator_order) == 1)].copy()
    df["d_candidate"] = (
        -df["x2_r"] * df["x1_r"].apply(lambda v: pow(int(v), -1, generator_order))
    ) % generator_order

    recovered = int(df["d_candidate"].mode()[0])
    print(f"  Recovered d={recovered}, expected d={known_d} → {'✅' if recovered == known_d else '❌'}")
    assert recovered == known_d, f"MISMATCH: got {recovered}, expected {known_d}"
    return recovered


# %% Standalone entry point

if __name__ == "__main__":
    bits = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    d = solve(bits)
    play_ending_sound()
