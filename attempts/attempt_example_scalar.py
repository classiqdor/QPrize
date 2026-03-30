# =============================================================================
# attempt_example_scalar — Reference implementation, Method A (Scalar Oracle)
#
# PURPOSE: Clean, well-commented reference for the scalar-oracle approach.
#          Intended as a readable baseline; optimizations go in numbered attempts.
#
# ALGORITHM: Shor's algorithm for ECDLP, scalar-index encoding.
#
#   The oracle register holds an integer k ∈ Z_n, where k is the scalar index
#   of an EC group element (i.e., the element equals k·G).
#
#   Oracle:   ecp_idx = initial_idx + x1·1 + x2·(−d) mod n
#                     = initial_idx + x1·g_step − x2·q_step mod n
#
#   After inverse QFT, the measurement peaks satisfy m1 + m2·d ≡ 0 (mod n),
#   so d = −x2_r · x1_r⁻¹ mod n.
#
# CLASSICAL PRECOMPUTATION (the "cheat"):
#   negq_steps[i] = (n − scalar_index(2^i · Q)) mod n
#   Computing scalar_index(Q) requires enumerating all n EC group elements,
#   which IS solving the discrete log classically. The quantum circuit then
#   performs arithmetic in Z_n — trivially easy classically. This approach
#   is only interesting as a demonstration, not as a genuine ECDLP solver.
#   See GUIDELINE.md "Genuine ECDLP vs. the Scalar-Encoding Flaw".
#
# COST: ~716 CX (4-bit), ~1252 CX (6-bit). Hardware-viable at 4-bit.
# =============================================================================

import math
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from classiq import *

from consts import PARAMS
from ec import point_add
from utils import timed, play_ending_sound


# -----------------------------------------------------------------------------
# Classical precomputation
# -----------------------------------------------------------------------------

def precompute_oracle_constants(params, var_len: int) -> tuple[list[int], list[int]]:
    """
    Derive g_steps and negq_steps from public curve parameters G and Q.
    d is never read — but building point_to_index implicitly computes it.

    Returns:
        g_steps[i]     = 2^i mod n          (scalar index of 2^i·G)
        negq_steps[i]  = n − idx(2^i·Q)     (additive inverse of scalar index of 2^i·Q)
    """
    p, a, n = params.p, params.a, params.n
    G_pt, Q_pt = params.G, params.Q

    # Enumerate the entire EC group to map EC points → scalar indices.
    # point_to_index[P] = k  iff  P = k·G
    point_to_index = {}
    cur = None           # None represents the identity element (k=0)
    for k in range(n + 1):
        point_to_index[cur] = k % n
        cur = point_add(cur, G_pt, p, a)

    # For each QPE bit i, record the step sizes for x1 (multiples of G)
    # and x2 (negative multiples of Q).
    g_steps, negq_steps = [], []
    cur_q = Q_pt
    for i in range(var_len):
        g_steps.append((1 << i) % n)                          # 2^i mod n
        negq_steps.append((n - point_to_index[cur_q]) % n)   # − idx(2^i·Q) mod n
        cur_q = point_add(cur_q, cur_q, p, a)                 # double Q in-place

    return g_steps, negq_steps


# -----------------------------------------------------------------------------
# solve(num_bits) — main entry point
# -----------------------------------------------------------------------------

def solve(num_bits: int) -> int:
    """
    Run Shor's ECDLP circuit (scalar-oracle variant) for the given bit size.
    Returns the recovered secret d and asserts it equals the expected value.
    """
    params  = PARAMS[num_bits]
    n       = params.n       # EC group order
    known_d = params.d       # used ONLY for final correctness check

    # var_len = number of QPE register bits = ceil(log2(n))
    var_len  = n.bit_length()
    idx_bits = n.bit_length()   # bits needed to represent an element of Z_n
    N        = 1 << var_len     # QPE register size (must satisfy N ≥ n)

    # Starting index for the oracle register (any non-zero value works;
    # choosing 2 avoids the identity element)
    initial_idx = 2

    g_steps, negq_steps = precompute_oracle_constants(params, var_len)

    print(f"\n[example_scalar] {num_bits}-bit | n={n} | solving for d...")

    # -------------------------------------------------------------------------
    # Circuit definition
    # -------------------------------------------------------------------------

    @qfunc
    def prepare_superposition(
        x1: Output[QArray[QBit]],
        x2: Output[QArray[QBit]],
    ) -> None:
        """Allocate and Hadamard the two QPE registers, creating |+⟩⊗2·var_len."""
        allocate(var_len, x1)
        allocate(var_len, x2)
        hadamard_transform(x1)
        hadamard_transform(x2)

    @qfunc
    def group_add_oracle(
        x1:      QArray[QBit],
        x2:      QArray[QBit],
        ecp_idx: Output[QNum[idx_bits, False, 0]],
    ) -> None:
        """
        Oracle: ecp_idx = initial_idx + x1·g_step − x2·q_step  (mod n)

        Each QPE bit x1[i] controls an addition of g_steps[i] = 2^i (mod n).
        Each QPE bit x2[i] controls an addition of negq_steps[i] = −d·2^i (mod n).
        Together this encodes the group index of P0 + x1·G − x2·Q.
        """
        allocate(idx_bits, False, 0, ecp_idx)
        ecp_idx ^= initial_idx      # set starting point

        # Controlled additions for x1 (multiples of G)
        for i in range(var_len):
            control(x1[i], lambda k=g_steps[i]:
                    modular_add_constant_inplace(n, k, ecp_idx))

        # Controlled additions for x2 (negative multiples of Q)
        for i in range(var_len):
            control(x2[i], lambda k=negq_steps[i]:
                    modular_add_constant_inplace(n, k, ecp_idx))

    @qfunc
    def extract_phase(x1: QArray[QBit], x2: QArray[QBit]) -> None:
        """Inverse QFT on both QPE registers to reveal the period."""
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

    # -------------------------------------------------------------------------
    # Synthesize
    # -------------------------------------------------------------------------

    qmod = create_model(
        main,
        constraints=Constraints(max_width=200),
        preferences=Preferences(optimization_level=1, timeout_seconds=3600),
    )
    with timed("Synthesize"):
        qprog = synthesize(qmod)

    ops = qprog.transpiled_circuit.count_ops
    print(f"  Qubits: {qprog.data.width} | Depth: {qprog.transpiled_circuit.depth} "
          f"| CX: {ops.get('cx', 'N/A')}")

    # -------------------------------------------------------------------------
    # Execute + post-process
    # -------------------------------------------------------------------------

    with timed("Execute"):
        res = execute(qprog).result_value()

    df = res.dataframe.sort_values("counts", ascending=False)

    def to_int(v):
        """Convert a Classiq result value (int, float, or bit array) to int."""
        if isinstance(v, (int, float)):
            return int(v)
        return sum(int(b) * (1 << i) for i, b in enumerate(v))

    # Scale raw measurements (fractions in [0,1)) back to frequency integers in Z_n
    df["x1_r"] = (df["x1"].apply(to_int) / N * n).round().astype(int) % n
    df["x2_r"] = (df["x2"].apply(to_int) / N * n).round().astype(int) % n

    # Keep only rows where x1_r is invertible mod n (gcd = 1)
    df = df[df["x1_r"].apply(lambda v: math.gcd(int(v), n) == 1)].copy()

    # Peak condition: m1 + m2·d ≡ 0 (mod n)  ⟹  d = −x2_r · x1_r⁻¹ mod n
    df["d_candidate"] = (
        -df["x2_r"] * df["x1_r"].apply(lambda v: pow(int(v), -1, n))
    ) % n

    recovered = int(df["d_candidate"].mode()[0])
    match = recovered == known_d
    print(f"  Recovered d={recovered}, expected d={known_d} → {'✅' if match else '❌'}")
    assert match, f"MISMATCH: got {recovered}, expected {known_d}"

    play_ending_sound()
    return recovered


if __name__ == "__main__":
    bits = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    solve(bits)
