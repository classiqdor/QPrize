# attempt_006B — 2026-03-29 19:00
#
# CHANGE: Restructure main into three named sub-functions per GUIDELINE.
# WHY: No algorithmic change vs 006. The split makes group_add_oracle —
#      the genuine EC arithmetic oracle — the clear target for optimization.
#      Hadamard and inverse-QFT layers are untouched.
#
#   prepare_superposition  — allocate + Hadamard the QPE registers x1, x2
#   group_add_oracle       — EC point register + controlled ec_scalar_mult_add
#   extract_phase          — inverse QFT on x1, x2
#
# Expected CX: identical to 006 (unverified for 4-bit; EC arithmetic is expensive).

import json
import math
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from classiq import *
from classiq.qmod.symbolic import subscript

from consts import PARAMS
from utils import timed, play_ending_sound


def ec_double(P, p, a):
    """Return 2·P on y² = x³ + a·x + b (mod p). P is [x, y]."""
    x, y = P
    s = (3 * x * x + a) * pow(2 * y, -1, p) % p
    xr = (s * s - 2 * x) % p
    yr = (s * (x - xr) - y) % p
    return [xr, yr % p]


def solve(num_bits: int) -> int:
    """
    Genuine Shor ECDLP with 3-part main structure.
    Oracle uses EC (x,y) coordinates; d never enters the circuit.
    """
    params  = PARAMS[num_bits]
    p       = params.p
    n       = params.n
    a       = params.a
    G_pt    = list(params.G)
    Q_pt    = list(params.Q)
    known_d = params.d        # used ONLY for final assertion

    var_len = n.bit_length()
    p_bits  = p.bit_length()

    P0    = ec_double(G_pt, p, a)
    neg_Q = [Q_pt[0], (p - Q_pt[1]) % p]

    print(f"\n[attempt_006B] {num_bits}-bit | p={p} | n={n} | d=??? (solving)")
    print(f"  P0={P0}  G={G_pt}  -Q={neg_Q}")

    # ------------------------------------------------------------------
    # Quantum types and helpers (close over p, p_bits)
    # ------------------------------------------------------------------

    class EllipticCurvePoint(QStruct):
        x: QNum[p_bits, False, 0]
        y: QNum[p_bits, False, 0]

    @qperm
    def mock_modular_inverse(x: Const[QNum], result: QNum, modulus: int) -> None:
        inverse_table = lookup_table(
            lambda v: pow(int(v), -1, modulus) if math.gcd(int(v), modulus) == 1 else 0,
            x,
        )
        result ^= subscript(inverse_table, x)

    @qperm
    def ec_point_add(ecp: EllipticCurvePoint, G: list[int], p: int) -> None:
        """In-place: ecp ← ecp + G.  Roetteler et al. 2017 Algorithm 1."""
        Gx, Gy   = G[0], G[1]
        n_bits   = p.bit_length()
        slope    = QNum()
        allocate(n_bits, slope)
        t0 = QNum()
        allocate(n_bits, t0)

        modular_add_constant_inplace(p, (-Gy) % p, ecp.y)
        modular_add_constant_inplace(p, (-Gx) % p, ecp.x)

        within_apply(
            lambda: mock_modular_inverse(ecp.x, t0, p),
            lambda: modular_multiply(p, t0, ecp.y, slope),
        )
        within_apply(
            lambda: modular_multiply(p, slope, ecp.x, t0),
            lambda: inplace_xor(t0, ecp.y),
        )
        within_apply(
            lambda: modular_square(p, slope, t0),
            lambda: (
                modular_subtract_inplace(p, t0, ecp.x),
                modular_negate_inplace(p, ecp.x),
                modular_add_constant_inplace(p, (3 * Gx) % p, ecp.x),
            ),
        )
        modular_multiply(p, slope, ecp.x, ecp.y)

        t1 = QNum()
        within_apply(
            lambda: mock_modular_inverse(ecp.x, t0, p),
            lambda: within_apply(
                lambda: (allocate(n_bits, t1), modular_multiply(p, t0, ecp.y, t1)),
                lambda: inplace_xor(t1, slope),
            ),
        )
        free(slope)

        modular_add_constant_inplace(p, (-Gy) % p, ecp.y)
        modular_negate_inplace(p, ecp.x)
        modular_add_constant_inplace(p, Gx, ecp.x)
        free(t0)

    @qperm
    def ec_scalar_mult_add(
        ecp: EllipticCurvePoint,
        k:   QArray[QBit],
        P:   list[int],
        p:   int,
        a:   int,
    ) -> None:
        current = P.copy()
        for i in range(k.size):
            control(k[i], lambda cur=current.copy(): ec_point_add(ecp, cur, p))
            if i < k.size - 1:
                current = ec_double(current, p, a)

    # ------------------------------------------------------------------
    # Circuit — three clearly named parts
    # ------------------------------------------------------------------

    @qfunc
    def prepare_superposition(x1: Output[QNum], x2: Output[QNum]) -> None:
        allocate(var_len, False, var_len, x1)
        allocate(var_len, False, var_len, x2)
        hadamard_transform(x1)
        hadamard_transform(x2)

    @qfunc
    def group_add_oracle(
        x1:  QNum,
        x2:  QNum,
        ecp: Output[EllipticCurvePoint],
    ) -> None:
        """Genuine EC arithmetic oracle: ecp = P0 + x1·G − x2·Q. d never used."""
        allocate(ecp)
        ecp.x ^= P0[0]
        ecp.y ^= P0[1]
        ec_scalar_mult_add(ecp, x1, G_pt, p, a)
        ec_scalar_mult_add(ecp, x2, neg_Q, p, a)

    @qfunc
    def extract_phase(x1: QNum, x2: QNum) -> None:
        invert(lambda: qft(x1))
        invert(lambda: qft(x2))

    @qfunc
    def main(
        x1:  Output[QNum],
        x2:  Output[QNum],
        ecp: Output[EllipticCurvePoint],
    ) -> None:
        prepare_superposition(x1, x2)
        group_add_oracle(x1, x2, ecp)
        extract_phase(x1, x2)

    # ------------------------------------------------------------------
    # Synthesize
    # ------------------------------------------------------------------

    qmod = create_model(
        main,
        constraints=Constraints(max_width=500),
        preferences=Preferences(optimization_level=1, timeout_seconds=3600),
    )
    with timed("Synthesize"):
        qprog = synthesize(qmod)

    ops   = qprog.transpiled_circuit.count_ops
    width = qprog.data.width
    depth = qprog.transpiled_circuit.depth
    cx    = ops.get("cx", None)
    print(f"  Qubits: {width} | Depth: {depth} | CX: {cx}")

    os.makedirs(os.path.join(os.path.dirname(__file__), "results"), exist_ok=True)
    result_path = os.path.join(os.path.dirname(__file__), "results",
                               f"attempt_006B_{num_bits}bit.json")
    with open(result_path, "w") as f:
        json.dump({"attempt": "attempt_006B_2026-03-29_1900",
                   "bits": num_bits, "width": width, "depth": depth, "cx": cx}, f, indent=2)

    # ------------------------------------------------------------------
    # Execute + post-process
    # ------------------------------------------------------------------

    with timed("Execute"):
        res = execute(qprog).result_value()

    df = res.dataframe.sort_values("counts", ascending=False)

    def to_freq(col):
        return df[col].apply(lambda v: round(float(v) * n) % n)

    df["x1_r"]  = to_freq("x1")
    df["x2_r"]  = to_freq("x2")
    df_valid    = df[df["x1_r"].apply(lambda v: math.gcd(int(v), n) == 1)].copy()
    df_valid["d_candidate"] = (
        -df_valid["x2_r"] * df_valid["x1_r"].apply(lambda v: pow(int(v), -1, n))
    ) % n

    recovered = int(df_valid["d_candidate"].mode()[0])
    match = recovered == known_d
    print(f"  Recovered d={recovered}, expected d={known_d} → {'✅' if match else '❌'}")
    assert match, f"MISMATCH: got {recovered}, expected {known_d}"
    play_ending_sound()
    return recovered


if __name__ == "__main__":
    bits = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    solve(bits)
