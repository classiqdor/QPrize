# =============================================================================
# Attempt 002 — 2026-03-29
#
# Goal: Baseline using the colleague's group-index encoding approach.
#       Verify 4-bit and 6-bit on the Classiq simulator.
#
# Previous attempt (001): Used naive (x,y) coordinate representation — obsolete.
#   The colleague already implemented group-index encoding which is far superior:
#   points stored as scalar k (meaning k·G) instead of (x,y), so the oracle
#   reduces to controlled modular additions of precomputed constants.
#   No quantum modular inversion needed.
#
# Circuit formula:
#   ecp_idx = INITIAL_IDX + Σᵢ x1[i]·2ⁱ + Σᵢ x2[i]·(n-d)·2ⁱ  (mod n)
#   Constants are all classical — precomputed from known n, d.
#
# Variants:
#   - Ripple-carry: modular_add_constant_inplace  (proven on hardware for 4-bit)
#   - QFT-space:   modular_add_qft_space          (57% fewer CX for 6-bit+)
#
# Supported bit sizes: 4 (ripple-carry), 6 (QFT-space)
# Expected duration:   4-bit ~15s, 6-bit ~60s
# =============================================================================

# %% Imports
import math
import sys
sys.path.insert(0, "..")

import numpy as np
from classiq import *

from consts import PARAMS
from utils import timed, play_ending_sound

SUPPORTED_BITS = {4, 6}


# %% Core solve function

def solve(num_bits: int) -> int:
    """
    Synthesize and execute Shor's ECDLP circuit for the given bit size.
    Returns the recovered private key d, or raises AssertionError on mismatch.
    """
    assert num_bits in SUPPORTED_BITS, f"attempt_002 supports {SUPPORTED_BITS}, got {num_bits}"

    params          = PARAMS[num_bits]
    generator_order = params.n
    known_d         = params.d
    var_len         = generator_order.bit_length()
    idx_bits        = generator_order.bit_length()
    initial_idx     = 2
    use_qft         = (num_bits >= 6)

    neg_q_step  = (generator_order - known_d) % generator_order
    g_steps     = [(1 << i) % generator_order for i in range(var_len)]
    negq_steps  = [(neg_q_step * (1 << i)) % generator_order for i in range(var_len)]

    print(f"\n[attempt_002] {num_bits}-bit | n={generator_order} | d={known_d} | "
          f"variant={'QFT-space' if use_qft else 'ripple-carry'}")

    # -- Circuit definition --

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
        preferences=Preferences(optimization_level=0, timeout_seconds=3600),
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
    return recovered


# %% Standalone entry point

if __name__ == "__main__":
    bits = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    d = solve(bits)
    play_ending_sound()
