# =============================================================================
# Attempt 011 — 2026-03-30 12:10
#
# CHANGE: Replace quantum modular arithmetic (multiply, square) with small
#   precomputed lookup tables. Keeps Roetteler 2017 Algorithm 1 structure,
#   but replaces the three expensive operations:
#     - modular_multiply(p, a, b, c)  →  mul_lookup(a, b, c)    [p² entries]
#     - modular_square(p, a, c)       →  sq_lookup(a, c)         [p  entries]
#     - modular_inverse_lookup        →  inv_lookup               [p  entries]
#
# WHY: example_ec costs ~130k CX. The bottleneck is modular_multiply and
#   modular_square. For competition sizes (p < 50), lookup tables for these
#   operations have p² ≤ 2500 entries — far cheaper than arithmetic synthesis.
#
# KEY DESIGN CHOICES:
#   1. Oracle register uses flat QNum ex, ey (NOT EllipticCurvePoint struct).
#      This is required because `bind([ex, ey], combined)` fails on struct
#      fields but works on top-level QNum variables.
#   2. mul_lookup(a, b, result) uses bind([a, b], ab) to create a single 2D
#      index for subscript(). The lookup_table([a,b]) orders entries as
#      tbl[b * 2^p_bits + a], which matches bind([a,b], ab) = a | (b<<p_bits).
#   3. All bind operations are between top-level QNums (no struct fields).
#
# SCALABILITY: NOT scalable to cryptographic sizes — tables have p² entries.
#   For p=2^256: p² ≈ 2^512 entries. Competition sizes (p < 50) only.
#
# LEGITIMACY: ✅ d is never computed or used. Precomputation is EC doublings.
#
# EXPECTED IMPROVEMENT: ~5-10× fewer CX than example_ec's ~130k CX.
#   6 additions × (5 mul + 1 sq + 2 inv) lookups each × ~table_size gates.
#
# PREVIOUS: attempt_example_ec (same structure, quantum arithmetic)
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

    Roetteler 2017 structure with lookup-table arithmetic. Returns d.
    """
    assert num_bits in SUPPORTED_BITS, f"attempt_011 supports {SUPPORTED_BITS}, got {num_bits}"

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

    print(f"\n[attempt_011] {num_bits}-bit | p={p} | n={n} | p_bits={p_bits} | var_len={var_len}")
    print(f"  inv table: {p} entries | mul table: {p}² = {p*p} entries")

    # -----------------------------------------------------------------------
    # Lookup-table modular arithmetic
    # All functions take top-level QNums (not struct fields) — required for bind.
    # -----------------------------------------------------------------------

    @qperm
    def inv_lookup(x: Const[QNum], result: QNum) -> None:
        """result ^= x⁻¹ mod p  (1D table, p entries)."""
        tbl = lookup_table(
            lambda v: pow(int(v), -1, p) if math.gcd(int(v), p) == 1 else 0,
            x,
        )
        result ^= subscript(tbl, x)

    @qperm
    def sq_lookup(a: Const[QNum], result: QNum) -> None:
        """result ^= a² mod p  (1D table, p entries)."""
        tbl = lookup_table(lambda av: (int(av) ** 2) % p, a)
        result ^= subscript(tbl, a)

    @qperm
    def mul_lookup(a: QNum, b: QNum, result: QNum) -> None:
        """
        result ^= a * b mod p  (2D table, p² entries).

        lookup_table([a, b]) orders entries as tbl[b * 2^p_bits + a].
        bind([a, b], ab) produces ab = a | (b << p_bits) = a + b * 2^p_bits.
        So subscript(tbl, ab) correctly indexes the 2D table. ✓

        NOTE: a and b must be top-level QNum variables (NOT struct fields).
        bind() does not support struct field accesses as source.
        """
        tbl = lookup_table(lambda av, bv: (int(av) * int(bv)) % p, [a, b])
        ab = QNum()
        bind([a, b], ab)
        result ^= subscript(tbl, ab)
        bind(ab, [a, b])

    # -----------------------------------------------------------------------
    # EC point addition (Roetteler 2017 Algorithm 1, lookup-table arithmetic)
    # Uses flat QNum ex, ey instead of EllipticCurvePoint struct.
    # -----------------------------------------------------------------------

    @qperm
    def ec_point_add(ex: QNum, ey: QNum, Gx: int, Gy: int) -> None:
        """In-place: (ex, ey) ← (ex, ey) + (Gx, Gy)."""
        slope = QNum()
        allocate(p_bits, slope)
        t0 = QNum()
        allocate(p_bits, t0)

        # Phase 1: shift to delta frame
        modular_add_constant_inplace(p, (-Gy) % p, ey)
        modular_add_constant_inplace(p, (-Gx) % p, ex)

        # Phase 2: slope = (y1-Gy) * (x1-Gx)⁻¹ mod p
        within_apply(
            lambda: inv_lookup(ex, t0),               # t0 = (x1-Gx)⁻¹
            lambda: mul_lookup(t0, ey, slope),         # slope = t0 * (y1-Gy)
        )

        # Phase 3: zero ey  [ey = y1-Gy = slope * (x1-Gx)]
        within_apply(
            lambda: mul_lookup(slope, ex, t0),         # t0 = slope * (x1-Gx)
            lambda: inplace_xor(t0, ey),                # ey ^= t0 → 0
        )

        # Phase 4: ex ← Gx - x3 = 3Gx + (x1-Gx) - slope²
        within_apply(
            lambda: sq_lookup(slope, t0),              # t0 = slope²
            lambda: (
                modular_subtract_inplace(p, t0, ex),   # ex = slope² - (x1-Gx)
                modular_negate_inplace(p, ex),           # ex = (x1-Gx) - slope²
                modular_add_constant_inplace(p, (3 * Gx) % p, ex),  # ex = Gx-x3
            ),
        )

        # Phase 5: ey ← y3 + Gy = slope * (Gx - x3)
        mul_lookup(slope, ex, ey)

        # Phase 6: uncompute slope
        t1 = QNum()
        within_apply(
            lambda: inv_lookup(ex, t0),                # t0 = (Gx-x3)⁻¹
            lambda: within_apply(
                lambda: (allocate(p_bits, t1), mul_lookup(t0, ey, t1)),
                lambda: inplace_xor(t1, slope),        # slope ^= t1 → 0
            ),
        )
        free(slope)

        # Phase 7: shift back to (x3, y3)
        modular_add_constant_inplace(p, (-Gy) % p, ey)
        modular_negate_inplace(p, ex)
        modular_add_constant_inplace(p, Gx, ex)

        free(t0)

    # -----------------------------------------------------------------------
    # Controlled scalar multiplication
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
    stem = f"attempt_011_{num_bits}bit"

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
        "attempt": "attempt_011_2026-03-30_1210",
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
