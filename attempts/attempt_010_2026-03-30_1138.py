# =============================================================================
# Attempt 010 — 2026-03-30 11:38
#
# CHANGE: Replace quantum EC arithmetic with a full precomputed lookup table
#   for each controlled EC point addition. This eliminates modular multiply,
#   square, and inverse entirely — each `ec_point_add_lookup` call is just
#   two table lookups and a 3-step XOR-swap (Bennett trick).
#
# WHY: attempt_006 / example_ec use Roetteler 2017 affine-coordinate arithmetic
#   inside `ec_point_add`. That function calls modular_multiply, modular_square,
#   and modular_inverse_lookup — all O(p_bits²) or worse. For 4-bit p=13
#   (p_bits=4), the whole circuit reaches ~130k CX and execution times out.
#
#   For competition sizes (p < 50, p_bits ≤ 6), the full lookup table has only
#   2^(2*p_bits) ≤ 4096 entries. Classiq's lookup_table+subscript synthesises
#   this as a multiplexed-CNOT with O(2^(2*p_bits) * 2*p_bits) gates — vastly
#   fewer than the arithmetic approach.
#
# ALGORITHM: Same as example_ec — Shor's ECDLP via Roetteler 2017 structure.
#   Oracle: ecp_flat ← packed(P0 + x1·G − x2·Q)  (coordinate register)
#
# ORACLE IMPLEMENTATION (new in this attempt):
#   ecp_flat: QNum of 2*p_bits = x | (y << p_bits) (packed coordinate register)
#   For each bit position i and each classical addend A = 2^i·G or −(2^i·Q):
#     1. Allocate old_bits = 0 (2*p_bits ancilla)
#     2. Forward table:  old_bits ^= f(ecp_flat)  where f packs (x,y)+A
#     3. XOR-swap:       ecp_flat ↔ old_bits        [ecp_flat = f(A), old_bits = old]
#     4. Inverse table:  old_bits ^= f_inv(ecp_flat) [old_bits zeroed]
#     5. free(old_bits)
#
# SCALABILITY: NOT scalable to cryptographic sizes — table has 2^(2*p_bits) entries.
#   For p_bits=256 that is 2^512 entries. Legitimate for competition sizes only.
#
# LEGITIMACY: ✅ d is never computed or used. Precomputation is EC doublings of G
#   and Q (public points only). Oracle register is genuine (x,y) ∈ F_p × F_p.
#
# KEY DESIGN: Oracle register is a flat QNum (not EllipticCurvePoint struct),
#   which avoids the `bind` restriction (bind cannot use struct field access).
#
# PREVIOUS: attempt_example_ec (same algorithm, arithmetic-based inverse)
# =============================================================================

# %% Imports
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from classiq import *
from classiq.qmod.symbolic import subscript

from consts import PARAMS
from ec import point_add
from utils import timed, play_ending_sound

SUPPORTED_BITS = set(PARAMS.keys())


# %% Classical EC helpers

def ec_double(P: list, p: int, a: int) -> list:
    """Return 2·P on y² = x³ + ax + b (mod p)."""
    x, y = P
    s  = (3 * x * x + a) * pow(2 * y, -1, p) % p
    xr = (s * s - 2 * x) % p
    yr = (s * (x - xr) - y) % p
    return [xr, yr % p]


def ec_add_packed(v: int, Gx: int, Gy: int, p: int, a: int, p_bits: int) -> int:
    """
    Lookup-table function: given packed register v = x | (y << p_bits),
    return the packed encoding of (x,y) + (Gx,Gy) mod p.

    v=0 is treated as the point at infinity (identity element).
    Out-of-range or invalid coordinates return 0 (identity).
    If the addition produces the point at infinity, returns 0.
    """
    mask = (1 << p_bits) - 1
    x = v & mask
    y = (v >> p_bits) & mask
    if x == 0 and y == 0:
        return Gx | (Gy << p_bits)
    if x >= p or y >= p:
        return 0
    result = point_add((x, y), (Gx, Gy), p, a)
    if result is None:
        return 0
    x3, y3 = result
    return x3 | (y3 << p_bits)


# %% Core solve function

def solve(num_bits: int) -> int:
    """
    Synthesize and execute Shor's ECDLP circuit for the given key size.

    Uses full precomputed lookup tables for EC point addition — eliminates all
    modular arithmetic from the oracle. Feasible only for competition-size curves
    (p < ~50). Returns the recovered private key d.
    """
    assert num_bits in SUPPORTED_BITS, f"attempt_010 supports {SUPPORTED_BITS}, got {num_bits}"

    params   = PARAMS[num_bits]
    p        = params.p
    n        = params.n
    a        = params.a
    G_pt     = list(params.G)
    Q_pt     = list(params.Q)
    known_d  = params.d           # used only for final assertion
    var_len  = n.bit_length()     # QPE register width
    p_bits   = p.bit_length()     # coordinate register width

    # Classical precomputation — only G and Q as public EC points; d never touched.
    P0           = ec_double(G_pt, p, a)            # starting oracle point = 2G
    p0_packed    = P0[0] | (P0[1] << p_bits)        # pack P0 as single int

    g_powers: list[list[int]] = [list(G_pt)]
    for _ in range(var_len - 1):
        g_powers.append(ec_double(g_powers[-1], p, a))

    neg_q_powers: list[list[int]] = []
    pt = list(Q_pt)
    for _ in range(var_len):
        neg_q_powers.append([pt[0], (p - pt[1]) % p])   # negate y → −(2^i·Q)
        pt = ec_double(pt, p, a)

    reg_bits = 2 * p_bits   # width of the packed coordinate register

    print(f"\n[attempt_010] {num_bits}-bit | p={p} | n={n} | p_bits={p_bits} | var_len={var_len}")
    print(f"  Table size per addition: 2^{reg_bits} = {1 << reg_bits} entries")

    # -----------------------------------------------------------------------
    # Lookup-table EC point addition on a flat QNum register
    # -----------------------------------------------------------------------

    @qperm
    def ec_point_add_lookup(ecp_flat: QNum, Gx: int, Gy: int) -> None:
        """
        In-place: ecp_flat ← packed((x,y) + (Gx, Gy)), implemented via
        a pair of lookup tables (Bennett reversible trick).

        ecp_flat encodes (x,y) as x | (y << p_bits).

        Steps:
          1. old_bits ^= f(ecp_flat)        [forward: new packed point]
          2. XOR-swap ecp_flat ↔ old_bits   [ecp_flat = new, old_bits = old]
          3. old_bits ^= f_inv(ecp_flat)    [inverse: uncompute old]
          4. free(old_bits)

        f(v)     = ec_add_packed(v, Gx, Gy)
        f_inv(v) = ec_add_packed(v, Gx, -Gy)  [subtracts the same point]
        f_inv(f(v)) = v, so step 3 zeros old_bits. ✓
        """
        neg_Gy = (p - Gy) % p

        old_bits = QNum()
        allocate(reg_bits, False, 0, old_bits)

        # Step 1: old_bits ← packed(ecp + (Gx,Gy))
        old_bits ^= subscript(
            lookup_table(
                lambda v, _Gx=Gx, _Gy=Gy: ec_add_packed(int(v), _Gx, _Gy, p, a, p_bits),
                ecp_flat,
            ),
            ecp_flat,
        )

        # Step 2: XOR-swap ecp_flat ↔ old_bits
        ecp_flat ^= old_bits
        old_bits ^= ecp_flat
        ecp_flat ^= old_bits

        # Step 3: old_bits ^= packed(ecp_flat - (Gx,Gy)) → zeroes old_bits
        old_bits ^= subscript(
            lookup_table(
                lambda v, _Gx=Gx, _nGy=neg_Gy: ec_add_packed(int(v), _Gx, _nGy, p, a, p_bits),
                ecp_flat,
            ),
            ecp_flat,
        )

        free(old_bits)

    # -----------------------------------------------------------------------
    # Controlled scalar multiplication: ecp_flat ← packed(ecp + k·P)
    # -----------------------------------------------------------------------

    @qperm
    def ec_scalar_mult_add(
        ecp_flat: QNum, k: QArray[QBit], powers: list[list[int]]
    ) -> None:
        """ecp_flat ← packed(ecp + k·P), powers = [P, 2P, 4P, ...] (classical)."""
        for i in range(k.size):
            pt = powers[i]
            control(k[i], lambda gx=pt[0], gy=pt[1]: ec_point_add_lookup(ecp_flat, gx, gy))

    # -----------------------------------------------------------------------
    # Three-part main circuit
    # -----------------------------------------------------------------------

    @qfunc
    def prepare_superposition(x1: Output[QNum], x2: Output[QNum]) -> None:
        """Allocate and Hadamard the two QPE registers."""
        allocate(var_len, False, var_len, x1)
        allocate(var_len, False, var_len, x2)
        hadamard_transform(x1)
        hadamard_transform(x2)

    @qfunc
    def group_add_oracle(
        x1:      QNum,
        x2:      QNum,
        ecp_flat: Output[QNum],
    ) -> None:
        """
        Oracle: ecp_flat = packed(P0 + x1·G − x2·Q)
        ecp_flat is a 2*p_bits QNum encoding (x,y) as x | (y << p_bits).
        d is never used.
        """
        allocate(reg_bits, False, 0, ecp_flat)
        ecp_flat ^= p0_packed             # initialise to P0
        ec_scalar_mult_add(ecp_flat, x1, g_powers)        # ecp ← P0 + x1·G
        ec_scalar_mult_add(ecp_flat, x2, neg_q_powers)    # ecp ← P0 + x1·G − x2·Q

    @qfunc
    def extract_phase(x1: QNum, x2: QNum) -> None:
        """Inverse QFT to expose the period (m1, m2)."""
        invert(lambda: qft(x1))
        invert(lambda: qft(x2))

    @qfunc
    def main(
        x1:      Output[QNum],
        x2:      Output[QNum],
        ecp_flat: Output[QNum],
    ) -> None:
        prepare_superposition(x1, x2)
        group_add_oracle(x1, x2, ecp_flat)
        extract_phase(x1, x2)

    # -----------------------------------------------------------------------
    # Synthesize
    # -----------------------------------------------------------------------

    qmod = create_model(
        main,
        constraints=Constraints(max_width=500),
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
    stem = f"attempt_010_{num_bits}bit"

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
    # Post-processing uses only x1 and x2 (QPE registers); ecp_flat is ignored.
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

    import json
    meta = {
        "attempt": "attempt_010_2026-03-30_1138",
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
