# =============================================================================
# Attempt 008 — 2026-03-29 18:59
#
# CHANGE: Refined coordinate-based scalable implementation.
#   - Uses named QNum variables (QNum("name", size) style) matching Classiq's
#     own library code, rather than the QNum[n, False, 0]() subscript form.
#     This improves synthesis introspection and error messages.
#   - All three temporaries (slope, t0, t1) allocated together before any
#     computation, making the resource lifecycle explicit and easy to audit.
#   - scalable_modular_inverse uses captured p_bits from the outer closure
#     (no inp.size call on a Const parameter).
#   - ec_point_add broken into clearly labelled phases matching the paper.
#
# WHY: attempt_007 introduced the Kaliski-based scalable modular inverse
#   (replacing the lookup-table in 004-1507). It is algorithmically correct
#   but uses the newer QNum[n,…]() subscript notation throughout; Classiq's
#   own library functions use the QNum("name", n) form, which is better
#   tested and produces labelled ancilla in synthesis output.
#
# ALGORITHM: Identical to attempt_007 —
#   Shor's ECDLP via Roetteler et al. 2017 (Algorithm 1).
#   Oracle: ecp ← P0 + x1·G − x2·Q  (coordinate register)
#   Modular inverse: Kaliski algorithm (modular_inverse_inplace) — O(n²) gates.
#
# SCALABILITY: Classical precomputation is O(bits) EC doublings (no enumeration).
#   Circuit size grows polynomially with key size.
#
# POST-PROCESSING (same as attempt_004+):
#   x1_r = round(x1 * n) % n
#   x2_r = round(x2 * n) % n
#   filter gcd(x1_r, n) == 1
#   d = (−x2_r · x1_r⁻¹) mod n
#
# PREVIOUS: attempt_007_2026-03-29_1840 — same algorithm, QNum[…]() style
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

SUPPORTED_BITS = set(PARAMS.keys())


# %% Classical EC helpers (polynomial-in-bits work, no group enumeration)

def ec_double(P, p, a):
    """Classical EC point doubling: returns 2·P on y² = x³ + ax + b (mod p)."""
    x, y = P
    s = (3 * x * x + a) * pow(2 * y, -1, p) % p
    xr = (s * s - 2 * x) % p
    yr = (s * (x - xr) - y) % p
    return [xr, yr % p]


def ec_add(P, Q_pt, p, a):
    """Classical EC point addition: returns P + Q_pt."""
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
    """Precompute [P, 2P, 4P, ..., 2^(k-1)·P] — O(k) EC doublings."""
    result = [list(P)]
    for _ in range(k - 1):
        result.append(ec_double(result[-1], p, a))
    return result


# %% Core solve function

def solve(num_bits: int) -> int:
    """
    Synthesize and execute Shor's ECDLP circuit for the given key size.

    Scalable: classical precomputation is O(bits) EC doublings.
    Quantum oracle: coordinate-based EC arithmetic with Kaliski modular inverse.
    Returns the recovered private key d, or raises AssertionError on mismatch.
    """
    assert num_bits in SUPPORTED_BITS, f"attempt_008 supports {SUPPORTED_BITS}, got {num_bits}"

    params   = PARAMS[num_bits]
    p        = params.p
    n        = params.n
    a        = params.a
    G_pt     = list(params.G)
    Q_pt     = list(params.Q)
    known_d  = params.d           # used only for final assertion
    var_len  = n.bit_length()     # QPE register width
    p_bits   = p.bit_length()     # coordinate register width

    # Classical precomputation — O(var_len) EC doublings each, no O(n) enumeration.
    P0           = ec_double(G_pt, p, a)
    g_powers     = build_powers(G_pt, p, a, var_len)
    q_powers     = build_powers(Q_pt, p, a, var_len)
    neg_q_powers = [[pt[0], (p - pt[1]) % p] for pt in q_powers]

    print(f"\n[attempt_008] {num_bits}-bit | p={p} | n={n} | p_bits={p_bits} | var_len={var_len}")
    print(f"  P0        = {P0}")
    print(f"  g_powers  = {[tuple(pt) for pt in g_powers]}")
    print(f"  -q_powers = {[tuple(pt) for pt in neg_q_powers]}")

    # -----------------------------------------------------------------------
    # Quantum type definitions — capture p, p_bits from outer scope
    # -----------------------------------------------------------------------

    class EllipticCurvePoint(QStruct):
        x: QNum[p_bits, False, 0]   # type: ignore[valid-type]
        y: QNum[p_bits, False, 0]   # type: ignore[valid-type]

    # -----------------------------------------------------------------------
    # Scalable modular inverse: result ^= inp⁻¹ mod p
    # Uses Kaliski algorithm (modular_inverse_inplace) — O(p_bits²) gates.
    # -----------------------------------------------------------------------

    @qperm
    def scalable_modular_inverse(inp: Const[QNum], result: QNum) -> None:
        """Compute result ^= inp⁻¹ mod p (Kaliski algorithm, scalable)."""
        # v is a copy of inp that modular_inverse_inplace will modify in place.
        # m holds the Kaliski ancilla (allocated by modular_inverse_inplace,
        # freed automatically by within_apply's uncompute step).
        v: QNum = QNum("inv_v", p_bits)
        m: QArray[QBit] = QArray[QBit]()
        allocate(p_bits, False, 0, v)
        v ^= inp                    # v = inp (copy; Const inp is not modified)
        within_apply(
            lambda: modular_inverse_inplace(p, v, m),   # v → v⁻¹, m allocated
            lambda: inplace_xor(v, result),              # result ^= v⁻¹
        )
        # within_apply uncompute: modular_inverse_inplace reversed → v = inp, m freed
        v ^= inp                    # v = inp XOR inp = 0
        free(v)

    # -----------------------------------------------------------------------
    # Quantum EC point addition: ecp ← ecp + (Gx, Gy)
    # Implements Roetteler 2017 Algorithm 1 (generic case; P ≠ ±A, P ≠ O).
    # All temporaries are cleaned up; function is a @qperm.
    # -----------------------------------------------------------------------

    @qperm
    def ec_point_add(ecp: EllipticCurvePoint, Gx: int, Gy: int) -> None:
        """In-place: ecp ← ecp + (Gx, Gy)."""
        # Allocate all temporaries up front (all start at 0).
        slope: QNum = QNum("slope", p_bits)
        t0:    QNum = QNum("t0",    p_bits)
        t1:    QNum = QNum("t1",    p_bits)
        allocate(p_bits, False, 0, slope)
        allocate(p_bits, False, 0, t0)
        allocate(p_bits, False, 0, t1)

        # --- Phase 1: shift into "delta" frame ---
        # ecp.y ← (y1 − Gy) mod p
        modular_add_constant_inplace(p, (-Gy) % p, ecp.y)
        # ecp.x ← (x1 − Gx) mod p
        modular_add_constant_inplace(p, (-Gx) % p, ecp.x)

        # --- Phase 2: compute slope = (y1−Gy) / (x1−Gx) mod p ---
        within_apply(
            lambda: scalable_modular_inverse(ecp.x, t0),        # t0 = (x1−Gx)⁻¹
            lambda: modular_multiply(p, t0, ecp.y, slope),       # slope = t0·(y1−Gy)
        )
        # After: slope set, t0 = 0.

        # --- Phase 3: zero out ecp.y (= y1−Gy = slope·(x1−Gx)) ---
        within_apply(
            lambda: modular_multiply(p, slope, ecp.x, t0),      # t0 = slope·(x1−Gx)
            lambda: inplace_xor(t0, ecp.y),                      # ecp.y = 0
        )
        # After: ecp.y = 0, t0 = 0.

        # --- Phase 4: compute ecp.x ← (Gx − x3) ---
        # x3 = slope² − x1 − Gx  ⟹  Gx − x3 = 2Gx + x1 − slope²
        # Starting value: ecp.x = x1 − Gx
        within_apply(
            lambda: modular_square(p, slope, t0),                     # t0 = slope²
            lambda: (
                modular_subtract_inplace(p, t0, ecp.x),               # ecp.x = slope² − (x1−Gx)
                modular_negate_inplace(p, ecp.x),                      # ecp.x = (x1−Gx) − slope²
                modular_add_constant_inplace(p, (3 * Gx) % p, ecp.x), # ecp.x = Gx − x3
            ),
        )
        # After: ecp.x = Gx − x3, t0 = 0.

        # --- Phase 5: set ecp.y ← (y3 + Gy) = slope·(Gx − x3) ---
        modular_multiply(p, slope, ecp.x, ecp.y)
        # After: ecp.y = y3 + Gy.

        # --- Phase 6: uncompute slope ---
        # slope = (y3+Gy) / (Gx−x3)  ⟹  use inverse of (Gx−x3) to recover slope, XOR to zero.
        within_apply(
            lambda: scalable_modular_inverse(ecp.x, t0),          # t0 = (Gx−x3)⁻¹
            lambda: within_apply(
                lambda: modular_multiply(p, t0, ecp.y, t1),        # t1 = t0·(y3+Gy) = slope
                lambda: inplace_xor(t1, slope),                     # slope ^= t1 → 0
            ),
        )
        free(slope)
        # After: slope = 0 (freed), t0 = 0, t1 = 0.

        # --- Phase 7: shift out of "delta" frame → final (x3, y3) ---
        modular_add_constant_inplace(p, (-Gy) % p, ecp.y)    # ecp.y = y3
        modular_negate_inplace(p, ecp.x)                       # ecp.x = x3 − Gx
        modular_add_constant_inplace(p, Gx, ecp.x)            # ecp.x = x3

        free(t0)
        free(t1)

    # -----------------------------------------------------------------------
    # Controlled scalar multiplication: ecp ← ecp + k·P
    # -----------------------------------------------------------------------

    @qperm
    def ec_scalar_mult_add(
        ecp: EllipticCurvePoint, k: QArray[QBit], powers: list
    ) -> None:
        """ecp ← ecp + k·P, where powers = [P, 2P, 4P, ...] (classical)."""
        for i in range(k.size):
            pt = powers[i]
            control(k[i], lambda gx=pt[0], gy=pt[1]: ec_point_add(ecp, gx, gy))

    # -----------------------------------------------------------------------
    # Main quantum circuit
    # -----------------------------------------------------------------------

    @qfunc
    def main(
        x1:  Output[QNum],
        x2:  Output[QNum],
        ecp: Output[EllipticCurvePoint],
    ) -> None:
        # Fractional QPE registers: measured value ∈ [0, 1)
        # Post-processing: m_i = round(x_i_measured · n) % n
        allocate(var_len, False, var_len, x1)
        allocate(var_len, False, var_len, x2)

        # Initialize coordinate register to P0 = 2·G (non-special starting point)
        allocate(ecp)
        ecp.x ^= P0[0]
        ecp.y ^= P0[1]

        # Hadamard superposition
        hadamard_transform(x1)
        hadamard_transform(x2)

        # Oracle: ecp ← P0 + x1·G − x2·Q
        ec_scalar_mult_add(ecp, x1, g_powers)        # + x1·G
        ec_scalar_mult_add(ecp, x2, neg_q_powers)    # + x2·(−Q)

        # Inverse QFT to expose period (m1, m2)
        invert(lambda: qft(x1))
        invert(lambda: qft(x2))

    # -----------------------------------------------------------------------
    # Synthesize
    # -----------------------------------------------------------------------

    qmod = create_model(
        main,
        constraints=Constraints(max_width=300),
        preferences=Preferences(optimization_level=1, timeout_seconds=3600),
    )
    with timed("Synthesize"):
        qprog = synthesize(qmod)

    ops      = qprog.transpiled_circuit.count_ops
    cx_count = ops.get("cx", "N/A")
    n_qubits = qprog.data.width
    depth    = qprog.transpiled_circuit.depth
    print(f"  Qubits: {n_qubits} | Depth: {depth} | CX: {cx_count}")

    results_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(results_dir, exist_ok=True)
    stem = f"attempt_008_{num_bits}bit"

    # Save raw Classiq circuit
    try:
        qprog.save(os.path.join(results_dir, f"{stem}.qprog"))
    except Exception as e:
        print(f"  Warning: could not save qprog: {e}")

    # -----------------------------------------------------------------------
    # Execute
    # -----------------------------------------------------------------------

    with timed("Execute"):
        df = execute(qprog).result_value().dataframe

    # -----------------------------------------------------------------------
    # Post-process: m1·d + m2 ≡ 0 (mod n) → d = −m2·m1⁻¹ mod n
    # -----------------------------------------------------------------------

    def to_freq(col):
        return df[col].apply(lambda v: round(float(v) * n) % n)

    df["x1_r"] = to_freq("x1")
    df["x2_r"] = to_freq("x2")
    df_valid = df[df["x1_r"].apply(lambda v: math.gcd(int(v), n) == 1)].copy()
    df_valid["d_cand"] = (
        -df_valid["x2_r"] * df_valid["x1_r"].apply(lambda v: pow(int(v), -1, n))
    ) % n

    recovered = int(df_valid["d_cand"].mode()[0])
    ok = recovered == known_d
    print(f"  Recovered d={recovered}, expected d={known_d} → {'✅' if ok else '❌'}")

    # Save human-readable result summary (per GUIDELINE.md)
    import json
    meta = {
        "attempt": "attempt_008_2026-03-29_1859",
        "bits": num_bits,
        "qubits": n_qubits,
        "depth": depth,
        "cx": cx_count,
        "gate_counts": {k: v for k, v in ops.items()},
        "decoded_d": recovered,
        "expected_d": known_d,
        "success": bool(ok),
    }
    meta_path = os.path.join(results_dir, f"{stem}_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  Meta saved to {meta_path}")

    assert ok, f"MISMATCH: got {recovered}, expected {known_d}"
    play_ending_sound()
    return recovered


# %% Standalone entry point

if __name__ == "__main__":
    bits = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    solve(bits)
