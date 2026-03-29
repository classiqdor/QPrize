# =============================================================================
# Attempt 005 — 2026-03-29
#
# Experiment: Truncated var_len (fewer QPE register bits) to reduce CX count.
#
# Background:
#   - 6-bit (n=31): full var_len=5, gives 1252 CX, 16q
#   - Hardware needs ≤600 CX for viable fidelity
#   - Question: can we use var_len=4 (1022 CX) or var_len=3 (778 CX) and
#     still recover d=18 correctly?
#
# Theory:
#   The QFT-based Shor circuit measures x1,x2 ∈ [0, 2^var_len) representing
#   fractions m1/2^var_len and m2/2^var_len. The peaks satisfy:
#     m1·d + m2 ≡ 0  (mod n)
#   With fewer var_len bits, the peak resolution decreases. For n=31 and
#   var_len=4 (N=16), the closest approximation to m/n with 4-bit precision
#   may still allow recovery if we round to nearest multiple.
#
# Results (expected):
#   var_len=5 (full): ✅ d=18 recovered, 1252 CX
#   var_len=4:        ?  TBD, 1022 CX
#   var_len=3:        ?  TBD, 778 CX
# =============================================================================

# %% Imports
import math
import os
import sys
# Support running from repo root or from attempts/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from classiq import *

from consts import PARAMS
from ec import point_add
from utils import timed, play_ending_sound


def compute_oracle_constants(params, var_len: int):
    """Compute negq_steps for given var_len using only public parameters."""
    p, a, n = params.p, params.a, params.n
    G_pt, Q_pt = params.G, params.Q

    point_to_index = {}
    cur = None
    for k in range(n + 1):
        point_to_index[cur] = k % n
        cur = point_add(cur, G_pt, p, a)

    g_steps = []
    q_steps = []
    cur_q = Q_pt
    for i in range(var_len):
        g_idx = (1 << i) % n
        q_idx = point_to_index[cur_q]
        g_steps.append(g_idx)
        q_steps.append((n - q_idx) % n)
        cur_q = point_add(cur_q, cur_q, p, a)

    return g_steps, q_steps


def solve_truncated(num_bits: int, var_len_override: int = None) -> int:
    """
    Shor ECDLP with optional var_len override (truncated register).

    If var_len_override is None, uses full precision (n.bit_length()).
    Returns recovered d, or raises AssertionError on mismatch.
    """
    params          = PARAMS[num_bits]
    generator_order = params.n
    known_d         = params.d
    full_var_len    = generator_order.bit_length()
    var_len         = var_len_override if var_len_override is not None else full_var_len
    idx_bits        = full_var_len  # ecp register always needs full precision
    initial_idx     = 2

    g_steps, negq_steps = compute_oracle_constants(params, var_len)

    print(f"\n[attempt_005] {num_bits}-bit | n={generator_order} | var_len={var_len} "
          f"(full={full_var_len}) | d=??? (solving)")
    print(f"  g_steps    = {g_steps}")
    print(f"  negq_steps = {negq_steps}")

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

    qmod = create_model(
        main,
        constraints=Constraints(max_width=200),
        preferences=Preferences(optimization_level=1, timeout_seconds=3600),
    )
    with timed("Synthesize"):
        qprog = synthesize(qmod)

    ops = qprog.transpiled_circuit.count_ops
    print(f"  Qubits: {qprog.data.width} | Depth: {qprog.transpiled_circuit.depth} | CX: {ops.get('cx', 'N/A')}")

    with timed("Execute"):
        res = execute(qprog).result_value()

    df = res.dataframe.sort_values("counts", ascending=False)
    N  = 1 << var_len  # Use truncated var_len for scaling

    def to_int(v):
        if isinstance(v, (int, float)): return int(v)
        return sum(int(b) * (1 << i) for i, b in enumerate(v))

    df["x1_r"] = (df["x1"].apply(to_int) / N * generator_order).round().astype(int) % generator_order
    df["x2_r"] = (df["x2"].apply(to_int) / N * generator_order).round().astype(int) % generator_order
    df = df[df["x1_r"].apply(lambda v: math.gcd(int(v), generator_order) == 1)].copy()
    df["d_candidate"] = (
        -df["x2_r"] * df["x1_r"].apply(lambda v: pow(int(v), -1, generator_order))
    ) % generator_order

    print(f"  Top candidates: {df['d_candidate'].value_counts().head(5).to_dict()}")
    recovered = int(df["d_candidate"].mode()[0])
    match = recovered == known_d
    print(f"  Recovered d={recovered}, expected d={known_d} → {'✅' if match else '❌'}")
    assert match, f"MISMATCH: got {recovered}, expected {known_d}"
    return recovered


# %% Standalone entry point

if __name__ == "__main__":
    bits = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    var_len_arg = int(sys.argv[2]) if len(sys.argv) > 2 else None

    d = solve_truncated(bits, var_len_arg)
    play_ending_sound()
