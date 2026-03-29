# attempt_004B — 2026-03-29 19:00
#
# CHANGE: Restructure main into three named sub-functions per GUIDELINE.
# WHY: No algorithmic change vs 004_1600. The split makes the oracle the
#      only thing to vary in future experiments, and keeps Hadamard /
#      inverse-QFT layers untouched.
#
#   prepare_superposition  — allocate + Hadamard x1, x2
#   group_add_oracle       — the modular scalar additions (the hard part)
#   extract_phase          — inverse QFT on x1, x2
#
# Expected CX: identical to 004_1600 (716 / 4-bit, 1252 / 6-bit).

import json
import math
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from classiq import *

from consts import PARAMS
from ec import point_add
from utils import timed, play_ending_sound

SUPPORTED_BITS = set(PARAMS.keys())


def compute_oracle_constants(params, var_len: int):
    """Derive negq_steps from public G, Q via EC arithmetic — d never used."""
    p, a, n = params.p, params.a, params.n
    G_pt, Q_pt = params.G, params.Q

    point_to_index = {}
    cur = None
    for k in range(n + 1):
        point_to_index[cur] = k % n
        cur = point_add(cur, G_pt, p, a)

    g_steps, negq_steps = [], []
    cur_q = Q_pt
    for i in range(var_len):
        g_idx = (1 << i) % n
        q_idx = point_to_index[cur_q]
        g_steps.append(g_idx)
        negq_steps.append((n - q_idx) % n)
        cur_q = point_add(cur_q, cur_q, p, a)

    return g_steps, negq_steps


def solve(num_bits: int) -> int:
    assert num_bits in SUPPORTED_BITS, f"attempt_004B supports {SUPPORTED_BITS}, got {num_bits}"

    params          = PARAMS[num_bits]
    generator_order = params.n
    known_d         = params.d        # used ONLY for final assertion
    var_len         = generator_order.bit_length()
    idx_bits        = generator_order.bit_length()
    initial_idx     = 2
    use_qft         = (num_bits >= 6)

    g_steps, negq_steps = compute_oracle_constants(params, var_len)

    print(f"\n[attempt_004B] {num_bits}-bit | n={generator_order} | d=??? | "
          f"variant={'QFT-space' if use_qft else 'ripple-carry'}")

    # ------------------------------------------------------------------
    # Circuit — three clearly named parts
    # ------------------------------------------------------------------

    @qfunc
    def prepare_superposition(
        x1: Output[QArray[QBit]],
        x2: Output[QArray[QBit]],
    ) -> None:
        allocate(var_len, x1)
        allocate(var_len, x2)
        hadamard_transform(x1)
        hadamard_transform(x2)

    if use_qft:
        @qfunc
        def group_add_oracle(
            x1:      QArray[QBit],
            x2:      QArray[QBit],
            ecp_phi: Output[QArray[QBit]],
        ) -> None:
            ecp = QNum[idx_bits, False, 0]()
            allocate(idx_bits, False, 0, ecp)
            ecp ^= initial_idx
            qft(ecp)
            bind(ecp, ecp_phi)
            for i in range(var_len):
                control(x1[i], lambda k=g_steps[i]:
                        modular_add_qft_space(generator_order, k, ecp_phi))
            for i in range(var_len):
                control(x2[i], lambda k=negq_steps[i]:
                        modular_add_qft_space(generator_order, k, ecp_phi))
            invert(lambda: qft(ecp_phi))

        @qfunc
        def extract_phase(x1: QArray[QBit], x2: QArray[QBit]) -> None:
            invert(lambda: qft(x1))
            invert(lambda: qft(x2))

        @qfunc
        def main(
            x1:      Output[QArray[QBit]],
            x2:      Output[QArray[QBit]],
            ecp_phi: Output[QArray[QBit]],
        ) -> None:
            prepare_superposition(x1, x2)
            group_add_oracle(x1, x2, ecp_phi)
            extract_phase(x1, x2)

    else:
        @qfunc
        def group_add_oracle(
            x1:      QArray[QBit],
            x2:      QArray[QBit],
            ecp_idx: Output[QNum[idx_bits, False, 0]],
        ) -> None:
            allocate(idx_bits, False, 0, ecp_idx)
            ecp_idx ^= initial_idx
            for i in range(var_len):
                control(x1[i], lambda k=g_steps[i]:
                        modular_add_constant_inplace(generator_order, k, ecp_idx))
            for i in range(var_len):
                control(x2[i], lambda k=negq_steps[i]:
                        modular_add_constant_inplace(generator_order, k, ecp_idx))

        @qfunc
        def extract_phase(x1: QArray[QBit], x2: QArray[QBit]) -> None:
            invert(lambda: qft(x1))
            invert(lambda: qft(x2))

        @qfunc
        def main(
            x1:      Output[QArray[QBit]],
            x2:      Output[QArray[QBit]],
            ecp_idx: Output[QNum[idx_bits, False, 0]],
        ) -> None:
            prepare_superposition(x1, x2)
            group_add_oracle(x1, x2, ecp_idx)
            extract_phase(x1, x2)

    # ------------------------------------------------------------------
    # Synthesize
    # ------------------------------------------------------------------

    qmod = create_model(
        main,
        constraints=Constraints(max_width=200),
        preferences=Preferences(optimization_level=1, timeout_seconds=3600),
    )
    with timed("Synthesize"):
        qprog = synthesize(qmod)

    ops = qprog.transpiled_circuit.count_ops
    width = qprog.data.width
    depth = qprog.transpiled_circuit.depth
    cx    = ops.get("cx", None)
    print(f"  Qubits: {width} | Depth: {depth} | CX: {cx}")

    os.makedirs(os.path.join(os.path.dirname(__file__), "results"), exist_ok=True)
    result_path = os.path.join(os.path.dirname(__file__), "results",
                               f"attempt_004B_{num_bits}bit.json")
    with open(result_path, "w") as f:
        json.dump({"attempt": "attempt_004B_2026-03-29_1900",
                   "bits": num_bits, "width": width, "depth": depth, "cx": cx}, f, indent=2)

    # ------------------------------------------------------------------
    # Execute + post-process
    # ------------------------------------------------------------------

    with timed("Execute"):
        res = execute(qprog).result_value()

    df  = res.dataframe.sort_values("counts", ascending=False)
    N   = 1 << var_len

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
    match = recovered == known_d
    print(f"  Recovered d={recovered}, expected d={known_d} → {'✅' if match else '❌'}")
    assert match, f"MISMATCH: got {recovered}, expected {known_d}"
    play_ending_sound()
    return recovered


if __name__ == "__main__":
    bits = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    solve(bits)
