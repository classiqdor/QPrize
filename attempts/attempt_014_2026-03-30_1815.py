# =============================================================================
# Attempt 014 — 2026-03-30 18:15
#
# CHANGE: Replace steps 3 and 7 of ec_point_add with a direct slope_lookup.
#
# WHY: In attempt_012, the two most expensive remaining operations per addition:
#
#   Step 3 (compute slope):
#     within_apply(inv_lookup → 118 CX compute × 2, body: modular_multiply → 2527 CX)
#     = 118 + 2527 + 118 = 2763 CX
#
#   Step 7 (uncompute slope):
#     within_apply(inv_lookup × 2, within_apply(modular_multiply × 2, xor))
#     = 118 + (2527 + cheap + 2527) + 118 = 5290 CX
#
#   Both steps compute slope = ey * inv(ex):
#     - At step 3: ex = x1-Gx, ey = y1-Gy, slope = (y1-Gy)/(x1-Gx)
#     - At step 7: ex = Gx-x3, ey = slope*(Gx-x3), so ey*inv(ex) = slope ✓
#
#   KEY INSIGHT: Both uses of slope are STANDALONE (not in within_apply COMPUTE
#   positions). So bind runs only ONCE, not twice. This avoids attempt_011's
#   problem where mul_lookup in COMPUTE positions doubled the bind overhead.
#
#   slope_lookup(ex, ey, result): packs ex||(ey<<p_bits) via bind, does a
#   2^(2*p_bits)-entry table lookup, unpacks. Replaces the whole within_apply.
#
#   Expected per-addition savings:
#     Step 3: 2763 - slope_lookup_cost ≈ 2763 - 2355 = 408 CX
#     Step 7: 5290 - slope_lookup_cost ≈ 5290 - 2355 = 2935 CX
#     Total: ~3343 CX × 6 additions = ~20k CX saved
#     Expected: 105k - 20k = ~85k CX
#
#   (2355 CX is a linear-scaling estimate: sq_lookup at 13 entries = 120 CX,
#    slope_lookup at 256 entries ≈ 120 × 256/13 ≈ 2360 CX)
#
# STRUCTURE: Uses flat QNum ex, ey (not EllipticCurvePoint struct) in
#   ec_point_add — required because bind() cannot access struct fields.
#
# ALGORITHM: Shor's ECDLP, Roetteler 2017 Algorithm 1 (affine coordinates).
#   Oracle: ecp ← P0 + x1·G − x2·Q  (coordinate register)
#
# SCALABILITY: NOT scalable — lookup tables have p entries (sq) or p² (slope).
# LEGITIMACY: ✅ d is never computed or used.
#
# PREVIOUS: attempt_012 (sq_lookup only, 105,554 CX),
#           attempt_011 (mul_lookup in COMPUTE, 136,106 CX — worse due to bind doubling)
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

    Like attempt_012 but replaces steps 3 and 7 (slope computation and
    uncomputation) with a direct 2D slope lookup table. Returns d.
    """
    assert num_bits in SUPPORTED_BITS, f"attempt_014 supports {SUPPORTED_BITS}, got {num_bits}"

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

    reg_bits = 2 * p_bits   # width of the packed coordinate register

    print(f"\n[attempt_014] {num_bits}-bit | p={p} | n={n} | p_bits={p_bits} | var_len={var_len}")
    print(f"  slope_lookup: {1 << reg_bits} packed entries | replaces steps 3+7 (was 2763+5290 CX)")

    # -----------------------------------------------------------------------
    # Quantum types
    # -----------------------------------------------------------------------

    class EllipticCurvePoint(QStruct):
        x: QNum[p_bits, False, 0]   # type: ignore[valid-type]
        y: QNum[p_bits, False, 0]   # type: ignore[valid-type]

    # -----------------------------------------------------------------------
    # Lookup tables
    # -----------------------------------------------------------------------

    @qperm
    def sq_lookup(a: Const[QNum], result: QNum) -> None:
        """result ^= a² mod p  (p entries, 1D, Const — no bind needed)."""
        tbl = lookup_table(lambda av: (int(av) ** 2) % p, a)
        result ^= subscript(tbl, a)

    @qperm
    def slope_lookup(ex: QNum, ey: QNum, result: QNum) -> None:
        """
        result ^= (ey * inv(ex)) mod p  (2D table, 2^(2*p_bits) packed entries).

        Packs [ex, ey] into a single register via bind to index the table.
        lookup_table([ex, ey]) orders entries as tbl[ey * 2^p_bits + ex],
        matching bind([ex, ey], exy) = ex | (ey << p_bits).

        This function is called OUTSIDE any within_apply, so bind runs only
        once (not doubled), avoiding attempt_011's overhead issue.
        """
        def slope_fn(xv, yv) -> int:
            x, y = int(xv), int(yv)
            if x == 0 or math.gcd(x, p) != 1:
                return 0
            return (y * pow(x, -1, p)) % p

        tbl = lookup_table(slope_fn, [ex, ey])
        exy = QNum()
        bind([ex, ey], exy)
        result ^= subscript(tbl, exy)
        bind(exy, [ex, ey])

    # -----------------------------------------------------------------------
    # EC point addition — uses flat ex, ey (not EllipticCurvePoint struct)
    # to enable bind inside slope_lookup.
    # -----------------------------------------------------------------------

    @qperm
    def ec_point_add(ex: QNum, ey: QNum, Gx: int, Gy: int) -> None:
        """In-place: (ex, ey) ← (ex, ey) + (Gx, Gy) mod p."""
        n_bits = p.bit_length()

        slope = QNum()
        allocate(n_bits, slope)
        t0 = QNum()
        allocate(n_bits, t0)

        # Steps 1–2: shift to delta frame
        modular_add_constant_inplace(p, (-Gy) % p, ey)
        modular_add_constant_inplace(p, (-Gx) % p, ex)

        # Step 3: slope = (y1-Gy) * (x1-Gx)⁻¹  (direct 2D lookup, no within_apply)
        # At this point: ex = x1-Gx, ey = y1-Gy
        # slope_lookup XORs ey*inv(ex) into slope (starts at 0)
        slope_lookup(ex, ey, slope)

        # Step 4: zero ey  [ey = slope * ex at this point]
        within_apply(
            lambda: modular_multiply(p, slope, ex, t0),
            lambda: inplace_xor(t0, ey),
        )

        # Step 5: ex ← Gx - x3  (sq_lookup from attempt_012)
        within_apply(
            lambda: sq_lookup(slope, t0),
            lambda: (
                modular_subtract_inplace(p, t0, ex),
                modular_negate_inplace(p, ex),
                modular_add_constant_inplace(p, (3 * Gx) % p, ex),
            ),
        )

        # Step 6: ey ← y3 + Gy = slope * (Gx - x3) = slope * ex
        modular_multiply(p, slope, ex, ey)

        # Step 7: uncompute slope (direct 2D lookup)
        # At this point: ex = Gx-x3, ey = slope*(Gx-x3)
        # slope_lookup computes ey*inv(ex) = slope*(Gx-x3)*inv(Gx-x3) = slope
        # XOR-ing zeroes slope.
        slope_lookup(ex, ey, slope)
        free(slope)

        # Step 8: restore to (x3, y3)
        modular_negate_inplace(p, ex)
        modular_add_constant_inplace(p, Gx, ex)
        modular_add_constant_inplace(p, (-Gy) % p, ey)

        free(t0)

    # -----------------------------------------------------------------------
    # Controlled scalar multiplication — works on flat (ex, ey)
    # -----------------------------------------------------------------------

    @qperm
    def ec_scalar_mult_add(
        ex: QNum, ey: QNum, k: QArray[QBit], powers: list[list[int]]
    ) -> None:
        """(ex, ey) ← (ex, ey) + k·P, powers = [P, 2P, ...] (classical)."""
        for i in range(k.size):
            pt = powers[i]
            control(k[i], lambda gx=pt[0], gy=pt[1]: ec_point_add(ex, ey, gx, gy))

    # -----------------------------------------------------------------------
    # Three-part main circuit — uses flat ex, ey for oracle register
    # -----------------------------------------------------------------------

    @qfunc
    def prepare_superposition(x1: Output[QNum], x2: Output[QNum]) -> None:
        allocate(var_len, False, var_len, x1)
        allocate(var_len, False, var_len, x2)
        hadamard_transform(x1)
        hadamard_transform(x2)

    @qfunc
    def group_add_oracle(
        x1: QNum, x2: QNum,
        ex: Output[QNum], ey: Output[QNum],
    ) -> None:
        """Oracle: (ex, ey) = P0 + x1·G − x2·Q  (genuine EC, d never used)."""
        allocate(p_bits, False, 0, ex)
        allocate(p_bits, False, 0, ey)
        ex ^= P0[0]
        ey ^= P0[1]
        ec_scalar_mult_add(ex, ey, x1, g_powers)
        ec_scalar_mult_add(ex, ey, x2, neg_q_powers)

    @qfunc
    def extract_phase(x1: QNum, x2: QNum) -> None:
        invert(lambda: qft(x1))
        invert(lambda: qft(x2))

    @qfunc
    def main(
        x1: Output[QNum], x2: Output[QNum],
        ex: Output[QNum], ey: Output[QNum],
    ) -> None:
        prepare_superposition(x1, x2)
        group_add_oracle(x1, x2, ex, ey)
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
    stem = f"attempt_014_{num_bits}bit"

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
    # Post-process (uses only x1, x2 — ex and ey columns are ignored)
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
        "attempt": "attempt_014_2026-03-30_1815",
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
