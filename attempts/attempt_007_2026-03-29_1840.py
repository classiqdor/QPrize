# =============================================================================
# Attempt 007 — 2026-03-29 18:40
#
# CHANGE: Scalable oracle — coordinate-based EC arithmetic with quantum
#         modular inverse (Kaliski algorithm), replacing group-index encoding.
#
# WHY: All previous working attempts (002–006) used GROUP-INDEX ENCODING:
#   - The quantum register holds an integer k meaning the group point k·G.
#   - To add the public key Q = d·G, the code builds a point-to-index lookup
#     table by iterating all n group elements:
#         for k in range(n):  point_to_index[k·G] = k   # O(n) work
#   - For small competition sizes (n=31, n=79) this is trivial, but for real
#     cryptographic sizes (n ≈ 2^256) it is completely infeasible.
#   - This is therefore NOT a scalable quantum algorithm.
#
# FIX: Represent the oracle register as actual (x, y) coordinates in Fp.
#   Classical precomputation: only O(var_len) EC doublings are needed:
#       g_powers[i]     = 2^i · G   (i doublings of G)
#       neg_q_powers[i] = -(2^i · Q)  (i doublings of Q, then negate)
#   This is O(bits) work — polynomial in key size, fully scalable.
#
#   Quantum oracle: controlled EC point additions applied to |(px, py)⟩.
#   Each addition uses the Roetteler et al. 2017 algorithm.
#
# WHY NOT attempt_004_1507 (previous coordinate attempt):
#   That attempt used `mock_modular_inverse` via a classical lookup table
#   (Classiq's `lookup_table`/`subscript`). A lookup table of size p is
#   O(2^p_bits) in circuit size — NOT scalable to large p.
#
# THIS ATTEMPT: Replace mock_modular_inverse with `scalable_modular_inverse`
#   built on Classiq's `modular_inverse_inplace` (Kaliski algorithm), which
#   runs in O(log²(p)) gates — fully scalable.
#
# ALGORITHM: Shor ECDLP via Roetteler et al. 2017 (Algorithm 1).
#   Oracle: ecp ← P0 + x1·G − x2·Q (in (x,y) coordinate register)
#
# POST-PROCESSING: Identical to attempt_004+:
#   d = −x2_r · x1_r^{−1} mod n,  filter gcd(x1_r, n) == 1
#
# PREVIOUS: attempt_006_2026-03-29_1828 — 6-bit: estimated ~850 CX (group-idx)
# SCALABILITY: O(bits^3) circuit size for arbitrary EC key size
# NOTE: More expensive per-gate than group-index encoding; correctness and
#       scalability take priority over minimizing CX for small instances.
# =============================================================================

# %% Imports
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from classiq import *

from consts import PARAMS
from utils import timed, play_ending_sound

SUPPORTED_BITS = set(PARAMS.keys())  # all sizes: 4–21


# %% Classical EC helpers (no quantum, no group enumeration)

def ec_double(P, p, a):
    """Classical EC doubling: returns 2·P on y² = x³ + ax + b (mod p)."""
    x, y = P
    s = (3 * x * x + a) * pow(2 * y, -1, p) % p
    xr = (s * s - 2 * x) % p
    yr = (s * (x - xr) - y) % p
    return [xr, yr % p]


def ec_add_classical(P, Q_pt, p, a):
    """Classical EC addition: returns P + Q_pt on the curve."""
    if P is None:
        return Q_pt
    if Q_pt is None:
        return P
    x1, y1 = P
    x2, y2 = Q_pt
    if x1 == x2:
        return ec_double(P, p, a) if y1 == y2 else None
    s = (y2 - y1) * pow(x2 - x1, -1, p) % p
    xr = (s * s - x1 - x2) % p
    yr = (s * (x1 - xr) - y1) % p
    return [xr, yr % p]


def build_powers(P, p, a, k):
    """Precompute [P, 2P, 4P, ..., 2^(k-1)·P] using k-1 doublings. O(k) work."""
    result = [list(P)]
    for _ in range(k - 1):
        result.append(ec_double(result[-1], p, a))
    return result


# %% Core solve function

def solve(num_bits: int) -> int:
    """
    Synthesize and execute Shor's ECDLP circuit for the given bit size.

    Oracle uses (x,y) coordinate encoding — scalable to arbitrary key sizes.
    Classical precomputation is O(bits) EC doublings (no group enumeration).
    Quantum modular inverse uses Kaliski algorithm (O(bits²) gates).

    Returns the recovered private key d, or raises AssertionError on mismatch.
    """
    assert num_bits in SUPPORTED_BITS, f"attempt_007 supports {SUPPORTED_BITS}, got {num_bits}"

    params   = PARAMS[num_bits]
    p        = params.p          # field prime
    n        = params.n          # group order
    a        = params.a          # curve parameter (0 for all competition curves)
    G_pt     = list(params.G)    # generator (public)
    Q_pt     = list(params.Q)    # public key Q = d·G (public, d unknown)
    known_d  = params.d          # used ONLY for final assertion
    var_len  = n.bit_length()    # bits for x1, x2 QPE registers
    p_bits   = p.bit_length()    # bits for (x, y) coordinate registers

    # Classical precomputation: O(var_len) doublings each — fully scalable.
    # Uses only G and Q as EC points; d is never accessed.
    P0           = ec_double(G_pt, p, a)           # initial point = 2·G
    g_powers     = build_powers(G_pt, p, a, var_len)
    q_powers     = build_powers(Q_pt, p, a, var_len)
    neg_q_powers = [[pt[0], (p - pt[1]) % p] for pt in q_powers]

    print(f"\n[attempt_007] {num_bits}-bit | p={p} | n={n} | p_bits={p_bits} | var_len={var_len}")
    print(f"  P0         = {P0}")
    print(f"  g_powers   = {[tuple(pt) for pt in g_powers]}")
    print(f"  -q_powers  = {[tuple(pt) for pt in neg_q_powers]}")
    print(f"  Oracle: coordinate encoding, Kaliski inverse (scalable)")

    # ------------------------------------------------------------------
    # Quantum data structures — defined inside solve() to close over p, p_bits
    # ------------------------------------------------------------------

    class EllipticCurvePoint(QStruct):
        x: QNum[p_bits, False, 0]   # type: ignore[valid-type]
        y: QNum[p_bits, False, 0]   # type: ignore[valid-type]

    @qperm
    def scalable_modular_inverse(inp: Const[QNum], result: QNum) -> None:
        """
        Compute result ^= inp^{-1} mod p using Kaliski algorithm.
        Scalable: O(p_bits^2) gates, works for any prime p of any size.

        Replaces mock_modular_inverse (lookup table) from attempt_004_1507.
        Interface: Const input, mutable result (same as mock_modular_inverse).
        """
        n_bits = inp.size
        v = QNum[n_bits, False, 0]()
        m_ancilla = QArray[QBit]()
        allocate(n_bits, False, 0, v)
        v ^= inp  # v = inp (copy, since modular_inverse_inplace modifies in place)

        # Compute v^{-1} in-place, XOR into result, then uncompute v back to inp.
        within_apply(
            lambda: modular_inverse_inplace(p, v, m_ancilla),  # v → v^{-1}
            lambda: inplace_xor(v, result),                     # result ^= v^{-1}
        )
        # After within_apply: v is restored to inp by uncomputation of Kaliski.

        v ^= inp   # v = inp XOR inp = 0
        free(v)

    @qperm
    def ec_point_add(ecp: EllipticCurvePoint, Gx: int, Gy: int) -> None:
        """
        In-place EC point addition: ecp ← ecp + (Gx, Gy).
        Implements Roetteler et al. 2017 Algorithm 1 (generic case, P ≠ ±A, P ≠ O).

        Steps follow the paper's reversible EC addition sequence, using
        scalable_modular_inverse instead of a lookup table.
        """
        slope = QNum[p_bits, False, 0]()
        t0    = QNum[p_bits, False, 0]()
        t1    = QNum[p_bits, False, 0]()
        allocate(p_bits, False, 0, slope)
        allocate(p_bits, False, 0, t0)

        # Step 1: ecp.y ← y1 − Gy  (mod p)
        modular_add_constant_inplace(p, (-Gy) % p, ecp.y)
        # Step 2: ecp.x ← x1 − Gx  (mod p)
        modular_add_constant_inplace(p, (-Gx) % p, ecp.x)

        # Step 3: slope = (y1 − Gy) / (x1 − Gx) mod p  (scalable inverse!)
        within_apply(
            lambda: scalable_modular_inverse(ecp.x, t0),        # t0 = (x1−Gx)^{−1}
            lambda: modular_multiply(p, t0, ecp.y, slope),       # slope = t0·(y1−Gy)
        )

        # Step 4: zero out ecp.y   (y1−Gy = slope·(x1−Gx))
        within_apply(
            lambda: modular_multiply(p, slope, ecp.x, t0),      # t0 = slope·(x1−Gx) = y1−Gy
            lambda: inplace_xor(t0, ecp.y),                      # ecp.y ^= t0 → 0
        )

        # Step 5: ecp.x ← Gx − x3  (where x3 = slope² − x1 − Gx)
        within_apply(
            lambda: modular_square(p, slope, t0),                # t0 = slope²
            lambda: (
                modular_subtract_inplace(p, t0, ecp.x),          # ecp.x = (x1−Gx) − slope²
                modular_negate_inplace(p, ecp.x),                 # ecp.x = slope² − x1 + Gx
                modular_add_constant_inplace(p, (3 * Gx) % p, ecp.x),  # ecp.x = Gx − x3
            ),
        )

        # Step 6: ecp.y ← y3 + Gy = slope·(Gx − x3)
        modular_multiply(p, slope, ecp.x, ecp.y)

        # Step 7: uncompute slope using inverse operations
        allocate(p_bits, False, 0, t1)
        within_apply(
            lambda: scalable_modular_inverse(ecp.x, t0),         # t0 = (Gx−x3)^{−1}
            lambda: within_apply(
                lambda: modular_multiply(p, t0, ecp.y, t1),      # t1 = t0·(y3+Gy) = slope
                lambda: inplace_xor(t1, slope),                   # slope ^= t1 → 0
            ),
        )
        free(slope)

        # Step 8: final register adjustment → result is (x3, y3)
        modular_add_constant_inplace(p, (-Gy) % p, ecp.y)   # ecp.y = y3+Gy−Gy = y3
        modular_negate_inplace(p, ecp.x)                      # ecp.x = −(Gx−x3) = x3−Gx
        modular_add_constant_inplace(p, Gx, ecp.x)           # ecp.x = x3

        free(t0)
        free(t1)

    @qperm
    def ec_scalar_mult_add(ecp: EllipticCurvePoint, k: QArray[QBit], powers: list) -> None:
        """
        ecp ← ecp + k·P  where powers = [P, 2P, 4P, ...] (classical, precomputed).
        k is in quantum superposition; each bit controls one EC addition.
        """
        for i in range(k.size):
            pt = powers[i]
            control(k[i], lambda gx=pt[0], gy=pt[1]: ec_point_add(ecp, gx, gy))

    # ------------------------------------------------------------------
    # Main quantum circuit
    # ------------------------------------------------------------------

    @qfunc
    def main(
        x1:  Output[QNum],
        x2:  Output[QNum],
        ecp: Output[EllipticCurvePoint],
    ) -> None:
        # x1, x2: fractional QNum so measured values lie in [0, 1)
        # Post-processing: x1_r = round(measured_x1 * n) mod n = frequency m1
        allocate(var_len, False, var_len, x1)
        allocate(var_len, False, var_len, x2)

        # Initialize ecp = P0 = 2·G
        allocate(ecp)
        ecp.x ^= P0[0]
        ecp.y ^= P0[1]

        # Hadamard superposition on x1 and x2
        hadamard_transform(x1)
        hadamard_transform(x2)

        # Oracle: ecp ← P0 + x1·G − x2·Q
        ec_scalar_mult_add(ecp, x1, g_powers)        # add x1·G
        ec_scalar_mult_add(ecp, x2, neg_q_powers)    # add x2·(−Q) = subtract x2·Q

        # Inverse QFT on x1 and x2 — reveals period (m1, m2)
        invert(lambda: qft(x1))
        invert(lambda: qft(x2))

    # ------------------------------------------------------------------
    # Synthesize
    # ------------------------------------------------------------------

    qmod = create_model(
        main,
        constraints=Constraints(max_width=300),
        preferences=Preferences(optimization_level=1, timeout_seconds=3600),
    )
    with timed("Synthesize"):
        qprog = synthesize(qmod)

    ops = qprog.transpiled_circuit.count_ops
    cx_count = ops.get("cx", "N/A")
    print(f"  Qubits: {qprog.data.width} | Depth: {qprog.transpiled_circuit.depth} | CX: {cx_count}")

    results_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(results_dir, exist_ok=True)
    result_path = os.path.join(results_dir, f"attempt_007_{num_bits}bit.json")
    try:
        qprog.save(result_path)
        print(f"  Saved to {result_path}")
    except Exception as e:
        print(f"  Warning: could not save qprog: {e}")

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    with timed("Execute"):
        df = execute(qprog).result_value().dataframe

    # ------------------------------------------------------------------
    # Post-process: peak condition m1·d + m2 ≡ 0 (mod n) → d = −m2·m1^{−1} mod n
    # ------------------------------------------------------------------

    def to_freq(col):
        # x1, x2 are fractional: measured value in [0,1), multiply by n to get frequency
        return df[col].apply(lambda v: round(float(v) * n) % n)

    df["x1_r"] = to_freq("x1")
    df["x2_r"] = to_freq("x2")
    df_valid = df[df["x1_r"].apply(lambda v: math.gcd(int(v), n) == 1)].copy()
    df_valid["d_candidate"] = (
        -df_valid["x2_r"] * df_valid["x1_r"].apply(lambda v: pow(int(v), -1, n))
    ) % n

    recovered = int(df_valid["d_candidate"].mode()[0])
    print(f"  Recovered d={recovered}, expected d={known_d} → {'✅' if recovered == known_d else '❌'}")
    assert recovered == known_d, f"MISMATCH: got {recovered}, expected {known_d}"
    return recovered


# %% Standalone entry point

if __name__ == "__main__":
    bits = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    d = solve(bits)
    play_ending_sound()
