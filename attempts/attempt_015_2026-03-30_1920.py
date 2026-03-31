# =============================================================================
# Attempt 015 — 2026-03-30 19:20
#
# CHANGE: Replace `modular_multiply` with `fast_mul` (schoolbook decomposition).
#
# WHY: modular_multiply costs 2527 CX isolated for p=13.
#   Classiq uses a QFT-based (Beauregard-style) multiplier — O(n²) controlled
#   rotations for n-bit inputs, decomposed into many CX gates.
#
#   fast_mul decomposes a*b mod p using bit-by-bit accumulation:
#     result += sum_{i: a[i]=1} (2^i * b) mod p
#   Each term uses:
#     1. 1D lookup table: temp ^= lookup_table(v → (2^i * v) % p, b)
#        — p entries, b is Const[QNum], NO bind needed (same as sq_lookup!)
#        — cost: ~120 CX × 2 (compute + uncompute in within_apply) = 240 CX
#     2. Controlled modular addition: control(a[i], modular_add_inplace(p, temp, result))
#        — adds temp to result only if bit i of a is set
#        — cost: ~80-100 CX (controlled ripple-carry add for 4-bit mod 13)
#
#   Per fast_mul: p_bits iterations × (240 + ~90) = 4 × 330 = ~1320 CX
#   vs modular_multiply: 2527 CX → saving ~1207 CX per call.
#
# KEY INSIGHT: All 1D lookup tables use Const[QNum] input — no bind needed.
#   This is the same property that makes sq_lookup efficient. fast_mul
#   decomposes the expensive quantum×quantum multiplication into:
#     - p_bits cheap 1D lookups (Const[QNum], same as sq_lookup)
#     - p_bits controlled modular additions
#
# EXPECTED SAVINGS: fast_mul replaces modular_multiply in steps 3,4,6,7.
#   Effective multiply count per addition (counting within_apply doublings):
#     Step 3 body: 1×  →  saves 1207 CX
#     Step 4 compute: 2×  →  saves 2414 CX
#     Step 6 standalone: 1×  →  saves 1207 CX
#     Step 7 inner compute: 2×  →  saves 2414 CX
#     Total per addition: ~7242 CX saved
#   × 6 additions: ~43k CX total saved
#   Expected CX: 105,554 - 43,452 ≈ 62,000 CX
#
# NOTE: fast_mul uses modular addition (not XOR) to accumulate partial products.
#   Result must start at 0 (all usages in ec_point_add satisfy this).
#   The inverse (used in within_apply uncompute) is automatic via modular_subtract.
#
# ALGORITHM: Shor's ECDLP, Roetteler 2017 Algorithm 1 (affine coordinates).
#   Oracle: ecp ← P0 + x1·G − x2·Q  (coordinate register)
#
# SCALABILITY: NOT scalable — 1D lookup tables have p entries.
# LEGITIMACY: ✅ d is never computed or used.
#
# PREVIOUS: attempt_012 (sq_lookup only, 105,554 CX),
#           attempt_014 (slope_lookup 2D bind — worse, 128,198 CX)
# =============================================================================

# %% Imports
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from classiq import *
from classiq.qmod.symbolic import subscript

from consts import PARAMS
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


# %% Core solve function

def solve(num_bits: int) -> int:
    """
    Synthesize and execute Shor's ECDLP circuit.

    Like attempt_012 but replaces modular_multiply with fast_mul (schoolbook
    decomposition via 1D Const[QNum] lookups + controlled modular additions).
    Returns the recovered private key d.
    """
    assert num_bits in SUPPORTED_BITS, f"attempt_015 supports {SUPPORTED_BITS}, got {num_bits}"

    params   = PARAMS[num_bits]
    p        = params.p
    n        = params.n
    a        = params.a
    G_pt     = list(params.G)
    Q_pt     = list(params.Q)
    known_d  = params.d
    var_len  = n.bit_length()
    p_bits   = p.bit_length()

    P0 = ec_double(G_pt, p, a)

    g_powers: list[list[int]] = [list(G_pt)]
    for _ in range(var_len - 1):
        g_powers.append(ec_double(g_powers[-1], p, a))

    neg_q_powers: list[list[int]] = []
    pt = list(Q_pt)
    for _ in range(var_len):
        neg_q_powers.append([pt[0], (p - pt[1]) % p])
        pt = ec_double(pt, p, a)

    print(f"\n[attempt_015] {num_bits}-bit | p={p} | n={n} | p_bits={p_bits} | var_len={var_len}")
    print(f"  fast_mul: {p_bits} iterations of (1D lookup + controlled add) | replaces modular_multiply (2527 CX)")

    # -----------------------------------------------------------------------
    # Quantum types
    # -----------------------------------------------------------------------

    class EllipticCurvePoint(QStruct):
        x: QNum[p_bits, False, 0]   # type: ignore[valid-type]
        y: QNum[p_bits, False, 0]   # type: ignore[valid-type]

    # -----------------------------------------------------------------------
    # 1D lookup tables (no bind — Const[QNum] single input)
    # -----------------------------------------------------------------------

    @qperm
    def modular_inverse_lookup(x: Const[QNum], result: QNum) -> None:
        """result ^= x⁻¹ mod p  (p entries)."""
        inv_table = lookup_table(
            lambda v: pow(int(v), -1, p) if math.gcd(int(v), p) == 1 else 0,
            x,
        )
        result ^= subscript(inv_table, x)

    @qperm
    def sq_lookup(a: Const[QNum], result: QNum) -> None:
        """result ^= a² mod p  (p entries)."""
        tbl = lookup_table(lambda av: (int(av) ** 2) % p, a)
        result ^= subscript(tbl, a)

    # -----------------------------------------------------------------------
    # fast_mul: schoolbook modular multiply via 1D Const lookups + mod adds
    # -----------------------------------------------------------------------

    @qperm
    def fast_mul(a: QNum, b: Const[QNum], result: QNum) -> None:
        """
        result += a*b mod p  (result must start at 0).

        Schoolbook decomposition: a*b = sum_{i} a[i] * (2^i * b) mod p.
        For each bit i of a (p_bits iterations):
          - Compute temp = (2^i * b) mod p via 1D Const lookup (no bind!)
          - Control on a[i]: result += temp mod p
          - Uncompute temp

        All 1D lookup tables use b as Const[QNum] — synthesized efficiently
        like sq_lookup (120 CX), with no bind overhead.
        """
        temp = QNum()
        for i in range(p_bits):
            within_apply(
                lambda ii=i: (
                    allocate(p_bits, temp),
                    temp ^= subscript(
                        lookup_table(
                            lambda v, ci=ii: (int(v) * (2 ** ci)) % p,
                            b,
                        ),
                        b,
                    )
                ),
                lambda ii=i: control(a[ii], lambda: modular_add_inplace(p, temp, result))
            )

    # -----------------------------------------------------------------------
    # EC point addition — replaces modular_multiply with fast_mul
    # -----------------------------------------------------------------------

    @qperm
    def ec_point_add(
        ecp:    EllipticCurvePoint,
        addend: list[int],
        p_int:  int,
    ) -> None:
        """In-place: ecp ← ecp + addend  (mod p)."""
        Gx, Gy = addend[0], addend[1]
        n_bits = p_int.bit_length()

        slope = QNum()
        allocate(n_bits, slope)
        t0 = QNum()
        allocate(n_bits, t0)

        # Steps 1–2: shift to delta frame
        modular_add_constant_inplace(p_int, (-Gy) % p_int, ecp.y)
        modular_add_constant_inplace(p_int, (-Gx) % p_int, ecp.x)

        # Step 3: slope = (y1-Gy) * (x1-Gx)⁻¹
        within_apply(
            lambda: modular_inverse_lookup(ecp.x, t0),
            lambda: fast_mul(t0, ecp.y, slope),   # slope starts at 0
        )

        # Step 4: zero ecp.y  (ey = slope * ex at this point)
        within_apply(
            lambda: fast_mul(slope, ecp.x, t0),   # t0 starts at 0
            lambda: inplace_xor(t0, ecp.y),
        )

        # Step 5: ecp.x ← Gx - x3  (sq_lookup, same as attempt_012)
        within_apply(
            lambda: sq_lookup(slope, t0),
            lambda: (
                modular_subtract_inplace(p_int, t0, ecp.x),
                modular_negate_inplace(p_int, ecp.x),
                modular_add_constant_inplace(p_int, (3 * Gx) % p_int, ecp.x),
            ),
        )

        # Step 6: ecp.y ← y3 + Gy = slope * (Gx - x3)
        fast_mul(slope, ecp.x, ecp.y)   # ecp.y starts at 0

        # Step 7: uncompute slope
        t1 = QNum()
        within_apply(
            lambda: modular_inverse_lookup(ecp.x, t0),
            lambda: within_apply(
                lambda: (allocate(n_bits, t1), fast_mul(t0, ecp.y, t1)),
                lambda: inplace_xor(t1, slope),
            ),
        )
        free(slope)

        # Step 8: restore ecp to (x3, y3)
        modular_negate_inplace(p_int, ecp.x)
        modular_add_constant_inplace(p_int, Gx, ecp.x)
        modular_add_constant_inplace(p_int, (-Gy) % p_int, ecp.y)

        free(t0)

    # -----------------------------------------------------------------------
    # Controlled scalar multiplication
    # -----------------------------------------------------------------------

    @qperm
    def ec_scalar_mult_add(
        ecp:     EllipticCurvePoint,
        k:       QArray[QBit],
        P_start: list[int],
        p_int:   int,
        a_int:   int,
    ) -> None:
        """ecp ← ecp + k·P_start (EC arithmetic, in-place)."""
        current = P_start.copy()
        for i in range(k.size):
            control(k[i], lambda cur=current.copy(): ec_point_add(ecp, cur, p_int))
            if i < k.size - 1:
                current = ec_double(current, p_int, a_int)

    # -----------------------------------------------------------------------
    # Three-part main circuit
    # -----------------------------------------------------------------------

    @qfunc
    def prepare_superposition(x1: Output[QNum], x2: Output[QNum]) -> None:
        allocate(var_len, False, var_len, x1)
        allocate(var_len, False, var_len, x2)
        hadamard_transform(x1)
        hadamard_transform(x2)

    @qfunc
    def group_add_oracle(
        x1:  QNum, x2: QNum,
        ecp: Output[EllipticCurvePoint],
    ) -> None:
        """Oracle: ecp = P0 + x1·G − x2·Q  (genuine EC arithmetic, d never used)."""
        allocate(ecp)
        ecp.x ^= P0[0]
        ecp.y ^= P0[1]
        ec_scalar_mult_add(ecp, x1, G_pt, p, a)
        ec_scalar_mult_add(ecp, x2, [Q_pt[0], (p - Q_pt[1]) % p], p, a)

    @qfunc
    def extract_phase(x1: QNum, x2: QNum) -> None:
        invert(lambda: qft(x1))
        invert(lambda: qft(x2))

    @qfunc
    def main(
        x1:  Output[QNum], x2: Output[QNum],
        ecp: Output[EllipticCurvePoint],
    ) -> None:
        prepare_superposition(x1, x2)
        group_add_oracle(x1, x2, ecp)
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
    stem = f"attempt_015_{num_bits}bit"

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
    # Post-process
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
        "attempt": "attempt_015_2026-03-30_1920",
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
