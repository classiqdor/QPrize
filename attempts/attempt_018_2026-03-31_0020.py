# =============================================================================
# Attempt 018 — 2026-03-31 00:20
#
# CHANGE: Fix fast_mul scoping issues via explicit Bennett trick (no within_apply).
#
# BUGS IN 015/016/017:
#   015: `temp ^= subscript(...)` inside lambda — SyntaxError (statement in expression)
#   016: `inplace_xor(temp, subscript(...))` — AttributeError: CParamScalar has no
#        get_handle_binding. inplace_xor expects quantum handles; subscript() returns
#        CParamScalar (lookup result). Only QNum.__ixor__ handles lookup results.
#   017: `def compute_i(ii=i): ... temp ^= ...` — UnboundLocalError: augmented
#        assignment `^=` makes `temp` local to compute_i; Python can't find it.
#
# FIX: Implement the Bennett trick manually inside fast_mul without within_apply.
#   Allocate `temp` once before the loop. For each bit i:
#     1. temp ^= subscript(tbl_i, b)        # XOR-load: temp = (2^i * b) mod p
#     2. control(a[i], modular_add_inplace)  # conditional add to result
#     3. temp ^= subscript(tbl_i, b)        # XOR-unload: temp = 0 (self-inverse)
#   Free temp after loop. All `^=` calls are at fast_mul body scope — no scoping issue.
#
# CORRECTNESS: XOR is self-inverse (temp ^= x; temp ^= x → temp unchanged).
#   After each iteration: temp = 0. After all iterations: temp = 0, free(temp) valid.
#   Accumulation: result = sum_{i: a[i]=1} (2^i * b) mod p = a*b mod p. ✓
#
# ALGORITHM: Shor's ECDLP, Roetteler 2017 Algorithm 1 (affine coordinates).
#   Oracle: ecp ← P0 + x1·G − x2·Q  (coordinate register)
#
# SCALABILITY: NOT scalable — 1D lookup tables have p entries.
# LEGITIMACY: ✅ d is never computed or used.
#
# PREVIOUS: attempt_017 (UnboundLocalError), attempt_012 (sq_lookup only, 105,554 CX)
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

    Like attempt_017 but fast_mul uses explicit double-XOR (no within_apply,
    no nested functions) to avoid Python scoping issues with augmented assignment.
    Returns the recovered private key d.
    """
    assert num_bits in SUPPORTED_BITS, f"attempt_018 supports {SUPPORTED_BITS}, got {num_bits}"

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

    print(f"\n[attempt_018] {num_bits}-bit | p={p} | n={n} | p_bits={p_bits} | var_len={var_len}")
    print(f"  fast_mul: {p_bits} iters × (XOR-load, controlled add, XOR-unload) — no within_apply")

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
    # fast_mul: manual Bennett trick — explicit double-XOR, no within_apply
    # -----------------------------------------------------------------------

    @qperm
    def fast_mul(a: QNum, b: Const[QNum], result: QNum) -> None:
        """
        result += a*b mod p  (result must start at 0).

        Schoolbook: a*b = sum_{i: a[i]=1} (2^i * b) mod p.
        For each bit i (p_bits iterations), manually implements Bennett trick:
          1. temp ^= subscript(tbl_i, b)   # XOR-load: temp = (2^i*b) mod p
          2. control(a[i], modular_add_inplace(p, temp, result))
          3. temp ^= subscript(tbl_i, b)   # XOR-unload: temp = 0 (XOR self-inverse)

        All `^=` are at fast_mul scope (not inside nested functions) — no scoping issues.
        temp is allocated once before the loop and freed after (temp=0 at each iteration end).
        """
        temp = QNum()
        allocate(p_bits, temp)
        for i in range(p_bits):
            tbl = lookup_table(lambda v, ci=i: (int(v) * (2 ** ci)) % p, b)
            temp ^= subscript(tbl, b)                                        # load
            control(a[i], lambda: modular_add_inplace(p, temp, result))      # conditional add
            temp ^= subscript(tbl, b)                                        # unload
        free(temp)

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
    stem = f"attempt_018_{num_bits}bit"

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
        "attempt": "attempt_018_2026-03-31_0020",
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
