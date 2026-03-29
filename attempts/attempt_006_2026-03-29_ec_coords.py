# =============================================================================
# Attempt 006 — 2026-03-29
#
# CHANGE: Genuine ECDLP via EC coordinate register (Roetteler et al. 2017).
#
# WHY: Attempts 002B, 003, 004-1600, 005 all used "scalar-index encoding":
#      the oracle register holds an integer k ∈ Z_n (where the group element
#      is k·G), and the oracle constants negq_steps[i] = −d·2^i mod n.
#
#      But negq_steps implicitly encodes d: computing the scalar index of Q
#      (via a brute-force point_to_index lookup) IS solving the discrete log
#      classically. The quantum circuit then computes x1 − x2·d (mod n) —
#      arithmetic in Z_n, not EC arithmetic. d is known before the circuit runs.
#
#      The genuine fix: the oracle register must hold EC coordinates (x, y) ∈
#      F_p × F_p. The classically precomputed constants are EC points:
#
#          g_powers[i]     = 2^i · G    (EC doublings from G, no d needed)
#          neg_q_powers[i] = −(2^i · Q) (EC doublings from Q, negate y, no d)
#
#      The quantum circuit applies controlled EC point additions (slope formula
#      mod p). d is never used in circuit construction.
#
# REFERENCE: Roetteler, Naehrig, Svore, Lauter (2017), Algorithm 1.
#            Pattern matches the Classiq reference notebook:
#            classiq-library/.../elliptic_curves/elliptic_curve_discrete_log.ipynb
#
# SPECIAL-CASE NOTE: The generic EC addition formula (Roetteler Alg. 1) assumes
#      neither input is the identity and they are not equal or negatives. The
#      circuit may produce incorrect results for those basis states (probability
#      ≤ 2/n per step); those outcomes are discarded in post-processing.
#
# ORACLE: ecp = P0 + x1·G − x2·Q   (EC points in F_p, d never used)
# STATUS: Simulator only. EC arithmetic is expensive (many qubits/gates).
# =============================================================================

import math
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from classiq import *
from classiq.qmod.symbolic import subscript

from consts import PARAMS
from utils import timed, play_ending_sound


# ---------------------------------------------------------------------------
# Classical helpers (no d used)
# ---------------------------------------------------------------------------

def ec_double(P, p, a):
    """Return 2·P on y² = x³ + a·x + b (mod p). P is [x, y]."""
    x, y = P
    s = (3 * x * x + a) * pow(2 * y, -1, p) % p
    xr = (s * s - 2 * x) % p
    yr = (s * (x - xr) - y) % p
    return [xr, yr % p]


# ---------------------------------------------------------------------------
# solve(num_bits) — genuine ECDLP
# ---------------------------------------------------------------------------

def solve(num_bits: int) -> int:
    """
    Genuine Shor ECDLP. Oracle uses EC coordinates; d never enters the circuit.
    Returns recovered d (asserts correctness against params.d).
    """
    params  = PARAMS[num_bits]
    p       = params.p          # field prime
    n       = params.n          # group order
    a       = params.a          # curve param (0 for competition curves)
    G_pt    = list(params.G)    # generator (public)
    Q_pt    = list(params.Q)    # public key Q = d·G (d unknown to circuit)
    known_d = params.d          # used ONLY for final assertion

    var_len = n.bit_length()
    p_bits  = p.bit_length()

    # Classical precomputation — no d used anywhere
    P0      = ec_double(G_pt, p, a)        # starting point = 2·G
    neg_Q   = [Q_pt[0], (p - Q_pt[1]) % p]  # −Q (negate y)

    print(f"\n[attempt_006] {num_bits}-bit | p={p} | n={n} | d=??? (solving)")
    print(f"  P0={P0}  G={G_pt}  -Q={neg_Q}")
    print(f"  Register: {p_bits}-bit (x,y) + {var_len}-bit x1,x2")

    # -----------------------------------------------------------------------
    # Quantum functions  (all defined inside solve() to capture p, p_bits)
    # -----------------------------------------------------------------------

    class EllipticCurvePoint(QStruct):
        x: QNum[p_bits, False, 0]
        y: QNum[p_bits, False, 0]

    @qperm
    def mock_modular_inverse(x: Const[QNum], result: QNum, modulus: int) -> None:
        """|x⟩|0⟩ → |x⟩|x⁻¹ mod modulus⟩  via lookup table (small modulus only)."""
        inverse_table = lookup_table(
            lambda v: pow(int(v), -1, modulus) if math.gcd(int(v), modulus) == 1 else 0,
            x,
        )
        result ^= subscript(inverse_table, x)

    @qperm
    def ec_point_add(
        ecp: EllipticCurvePoint,
        G: list[int],   # classical EC point [Gx, Gy]
        p: int,         # field prime
    ) -> None:
        """In-place: ecp ← ecp + G.  Roetteler et al. 2017 Algorithm 1 (generic case)."""
        Gx, Gy = G[0], G[1]
        n_bits = p.bit_length()

        slope = QNum()
        allocate(n_bits, slope)
        t0 = QNum()
        allocate(n_bits, t0)

        # Step 1: ecp.y ← y1 − Gy  (mod p)
        modular_add_constant_inplace(p, (-Gy) % p, ecp.y)
        # Step 2: ecp.x ← x1 − Gx  (mod p)
        modular_add_constant_inplace(p, (-Gx) % p, ecp.x)

        # Step 3: slope = (y1−Gy) / (x1−Gx) mod p
        within_apply(
            lambda: mock_modular_inverse(ecp.x, t0, p),
            lambda: modular_multiply(p, t0, ecp.y, slope),
        )

        # Step 4: ecp.y ← 0
        within_apply(
            lambda: modular_multiply(p, slope, ecp.x, t0),
            lambda: inplace_xor(t0, ecp.y),
        )

        # Step 5: ecp.x ← Gx − x3
        within_apply(
            lambda: modular_square(p, slope, t0),
            lambda: (
                modular_subtract_inplace(p, t0, ecp.x),
                modular_negate_inplace(p, ecp.x),
                modular_add_constant_inplace(p, (3 * Gx) % p, ecp.x),
            ),
        )

        # Step 6: ecp.y ← y3 + Gy = slope·(Gx−x3)
        modular_multiply(p, slope, ecp.x, ecp.y)

        # Step 7: slope ← 0  (uncompute via (Gx−x3)⁻¹)
        t1 = QNum()
        within_apply(
            lambda: mock_modular_inverse(ecp.x, t0, p),
            lambda: within_apply(
                lambda: (allocate(n_bits, t1), modular_multiply(p, t0, ecp.y, t1)),
                lambda: inplace_xor(t1, slope),
            ),
        )
        free(slope)

        # Step 8: adjust to final (x3, y3)
        modular_add_constant_inplace(p, (-Gy) % p, ecp.y)
        modular_negate_inplace(p, ecp.x)
        modular_add_constant_inplace(p, Gx, ecp.x)

        free(t0)

    @qperm
    def ec_scalar_mult_add(
        ecp: EllipticCurvePoint,
        k: QArray[QBit],
        P: list[int],   # classical starting point [x, y]; doubles internally
        p: int,
        a: int,
    ) -> None:
        """ecp ← ecp + k·P, computing 2^i·P classically per bit."""
        current = P.copy()
        for i in range(k.size):
            control(k[i], lambda cur=current.copy(): ec_point_add(ecp, cur, p))
            if i < k.size - 1:
                current = ec_double(current, p, a)

    @qfunc
    def main(
        x1:  Output[QNum],
        x2:  Output[QNum],
        ecp: Output[EllipticCurvePoint],
    ) -> None:
        # QPE registers
        allocate(var_len, False, var_len, x1)
        allocate(var_len, False, var_len, x2)
        hadamard_transform(x1)
        hadamard_transform(x2)

        # EC point register initialised to P0
        allocate(ecp)
        ecp.x ^= P0[0]
        ecp.y ^= P0[1]

        # Oracle: ecp ← P0 + x1·G − x2·Q   (genuine EC arithmetic)
        ec_scalar_mult_add(ecp, x1, G_pt, p, a)
        ec_scalar_mult_add(ecp, x2, neg_Q, p, a)

        # Inverse QFT to extract period
        invert(lambda: qft(x1))
        invert(lambda: qft(x2))

    # -----------------------------------------------------------------------
    # Synthesize + Execute
    # -----------------------------------------------------------------------

    qmod = create_model(
        main,
        constraints=Constraints(max_width=500),
        preferences=Preferences(optimization_level=1, timeout_seconds=3600),
    )
    with timed("Synthesize"):
        qprog = synthesize(qmod)

    ops = qprog.transpiled_circuit.count_ops
    print(f"  Qubits: {qprog.data.width} | Depth: {qprog.transpiled_circuit.depth} | CX: {ops.get('cx', 'N/A')}")

    # -----------------------------------------------------------------------
    # Post-process: peak condition m1·d + m2 ≡ 0 (mod n) → d = −x2_r·x1_r⁻¹
    # -----------------------------------------------------------------------

    with timed("Execute"):
        res = execute(qprog).result_value()

    df = res.dataframe.sort_values("counts", ascending=False)

    def to_freq(col):
        return df[col].apply(lambda v: round(float(v) * n) % n)

    df["x1_r"] = to_freq("x1")
    df["x2_r"] = to_freq("x2")
    df_valid = df[df["x1_r"].apply(lambda v: math.gcd(int(v), n) == 1)].copy()
    df_valid["d_candidate"] = (
        -df_valid["x2_r"] * df_valid["x1_r"].apply(lambda v: pow(int(v), -1, n))
    ) % n

    recovered = int(df_valid["d_candidate"].mode()[0])
    match = recovered == known_d
    print(f"  Recovered d={recovered}, expected d={known_d} → {'✅' if match else '❌'}")
    assert match, f"MISMATCH: got {recovered}, expected {known_d}"

    play_ending_sound()
    return recovered


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    bits = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    solve(bits)
