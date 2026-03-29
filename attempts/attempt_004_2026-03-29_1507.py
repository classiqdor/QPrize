# attempt_004 — 2026-03-29 15:07
#
# CHANGE: Replace group-index encoding with actual elliptic curve arithmetic.
#
# WHY: Attempts 002–003 used "group-index encoding" which precomputes the
#      oracle constants from d directly:
#          neg_q_step = (n - d) % n
#      This is circular — you can't build that oracle without already knowing d.
#      The algorithm was solving "given d, find d", not ECDLP.
#
#      The correct approach: the oracle must be built from the *known* public
#      points G and Q only. We classically precompute the EC point multiples
#          G, 2G, 4G, ..., 2^(k-1)*G
#          -Q, -2Q, -4Q, ..., -2^(k-1)*Q
#      using repeated EC doubling (no knowledge of d required), and then apply
#      controlled quantum EC point additions to an (x, y) coordinate register.
#
# ORACLE: ecp = P0 + x1*G - x2*Q   (working with actual EC points mod p)
#
# ALGORITHM: Shor's ECDLP via Roetteler et al. 2017, adapted from the Classiq
#            reference notebook:
#            classiq-library/.../elliptic_curves/elliptic_curve_discrete_log.ipynb
#
# POST-PROCESSING: peak condition m1*d + m2 ≡ 0 (mod n)
#                  => d = -x2_r * x1_r^(-1) mod n,  filter gcd(x1_r, n) == 1
#
# NOTE: This uses mock_modular_inverse (lookup table) which is feasible only
#       for the small field primes in the competition (p=13, p=43, etc.).
#       For larger primes, replace with modular_inverse_inplace (Kaliski).
#
# QUBIT ESTIMATE: 2*p_bits (ecp) + 2*var_len (x1,x2) + aux ~ 40+ for 4-bit.
#                 This is larger than attempts 002-003 but actually correct.

import math
import numpy as np
from classiq import *
from classiq.qmod.symbolic import subscript
from consts import PARAMS, EllipticCurve
from utils import timed, play_ending_sound


# ---------------------------------------------------------------------------
# Classical EC helpers (no quantum)
# ---------------------------------------------------------------------------

def ec_double_classical(P, p, a):
    """Returns 2*P on curve y^2 = x^3 + a*x + b (mod p)."""
    x, y = P
    s = (3 * x * x + a) * pow(2 * y, -1, p) % p
    xr = (s * s - 2 * x) % p
    yr = (s * (x - xr) - y) % p
    return [xr, yr % p]


def ec_add_classical(P, Q_pt, p, a):
    """Returns P + Q_pt on the curve."""
    if P is None:
        return Q_pt
    if Q_pt is None:
        return P
    x1, y1 = P
    x2, y2 = Q_pt
    if x1 == x2:
        if y1 == y2:
            return ec_double_classical(P, p, a)
        return None  # P + (-P) = point at infinity
    s = (y2 - y1) * pow(x2 - x1, -1, p) % p
    xr = (s * s - x1 - x2) % p
    yr = (s * (x1 - xr) - y1) % p
    return [xr, yr % p]


def build_powers(P, p, a, k):
    """Classically compute P, 2P, 4P, ..., 2^(k-1)*P. Returns list of [x,y]."""
    result = [list(P)]
    for _ in range(k - 1):
        result.append(ec_double_classical(result[-1], p, a))
    return result


# ---------------------------------------------------------------------------
# solve(num_bits)
# ---------------------------------------------------------------------------

def solve(num_bits: int) -> int:
    params      = PARAMS[num_bits]
    p           = params.p          # field prime
    n           = params.n          # group order
    a           = params.a          # curve parameter (0 for competition curves)
    G_pt        = list(params.G)    # generator point (public, known)
    Q_pt        = list(params.Q)    # target point Q = d*G (public, known, d unknown)
    var_len     = n.bit_length()    # bits for x1, x2 registers
    p_bits      = p.bit_length()    # bits for (x, y) coordinates

    # Initial point: use 2*G (safe non-special starting point)
    P0 = ec_double_classical(G_pt, p, a)

    # Classically precompute: G, 2G, 4G, ..., 2^(var_len-1)*G
    g_powers = build_powers(G_pt, p, a, var_len)

    # Classically precompute: -Q, -2Q, ..., -2^(var_len-1)*Q
    # Negation: -(x, y) = (x, p-y) on the curve.
    # We compute Q, 2Q, 4Q, ... by doubling, then negate.
    q_powers    = build_powers(Q_pt, p, a, var_len)
    neg_q_powers = [[pt[0], (p - pt[1]) % p] for pt in q_powers]

    # ------------------------------------------------------------------
    # Quantum data structures — defined inside solve() to close over p, p_bits
    # ------------------------------------------------------------------

    class EllipticCurvePoint(QStruct):
        x: QNum[p_bits, False, 0]
        y: QNum[p_bits, False, 0]

    @qperm
    def mock_modular_inverse(inp: Const[QNum], result: QNum) -> None:
        """Lookup-table modular inverse: result ^= inp^(-1) mod p."""
        inv_table = lookup_table(
            lambda v: pow(int(v), -1, p) if math.gcd(int(v), p) == 1 else 0,
            inp,
        )
        result ^= subscript(inv_table, inp)

    @qperm
    def ec_point_add(ecp: EllipticCurvePoint, Gx: int, Gy: int) -> None:
        """In-place EC point addition: ecp <- ecp + (Gx, Gy).
        Implements Roetteler et al. 2017 Algorithm 1 (generic case).
        Requires ecp ≠ (Gx, Gy) and ecp ≠ -(Gx, Gy) and ecp ≠ O.
        """
        slope = QNum[p_bits, False, 0]()
        t0    = QNum[p_bits, False, 0]()
        t1    = QNum[p_bits, False, 0]()
        allocate(p_bits, False, 0, slope)
        allocate(p_bits, False, 0, t0)

        # Step 1: ecp.y <- y1 - Gy  (mod p)
        modular_add_constant_inplace(p, (-Gy) % p, ecp.y)
        # Step 2: ecp.x <- x1 - Gx  (mod p)
        modular_add_constant_inplace(p, (-Gx) % p, ecp.x)

        # Step 3: slope = (y1 - Gy) / (x1 - Gx)  (mod p)
        within_apply(
            lambda: mock_modular_inverse(ecp.x, t0),   # t0 = (x1-Gx)^-1
            lambda: modular_multiply(p, t0, ecp.y, slope),   # slope = t0 * (y1-Gy)
        )

        # Step 4: ecp.y <- 0  (y1-Gy = slope*(x1-Gx), XOR to zero)
        within_apply(
            lambda: modular_multiply(p, slope, ecp.x, t0),  # t0 = slope*(x1-Gx) = y1-Gy
            lambda: inplace_xor(t0, ecp.y),                 # ecp.y ^= t0 -> 0
        )

        # Step 5: ecp.x <- x2 - x3  (where x3 = slope^2 - x1 - x2, x2=Gx)
        within_apply(
            lambda: modular_square(p, slope, t0),                         # t0 = slope^2
            lambda: (
                modular_subtract_inplace(p, t0, ecp.x),                   # ecp.x = slope^2 - (x1-Gx)
                modular_negate_inplace(p, ecp.x),                          # ecp.x = (x1-Gx) - slope^2
                modular_add_constant_inplace(p, (3 * Gx) % p, ecp.x),    # ecp.x = x1 - slope^2 + 2*Gx = Gx - x3
            ),
        )

        # Step 6: ecp.y <- y3 + Gy  = slope*(Gx - x3)
        modular_multiply(p, slope, ecp.x, ecp.y)

        # Step 7: slope <- 0  (uncompute via t0 = (Gx-x3)^-1, t1 = slope)
        allocate(p_bits, False, 0, t1)
        within_apply(
            lambda: mock_modular_inverse(ecp.x, t0),         # t0 = (Gx-x3)^-1
            lambda: within_apply(
                lambda: modular_multiply(p, t0, ecp.y, t1),  # t1 = t0*(y3+Gy) = slope
                lambda: inplace_xor(t1, slope),               # slope ^= t1 -> 0
            ),
        )
        free(slope)

        # Step 8: adjust registers to final (x3, y3)
        modular_add_constant_inplace(p, (-Gy) % p, ecp.y)    # ecp.y = y3 + Gy - Gy = y3
        modular_negate_inplace(p, ecp.x)                      # ecp.x = x3 - Gx
        modular_add_constant_inplace(p, Gx, ecp.x)           # ecp.x = x3

        free(t0)
        free(t1)

    @qperm
    def ec_scalar_mult_add(ecp: EllipticCurvePoint, k: QArray[QBit], powers: list) -> None:
        """Compute ecp <- ecp + k * P, where powers = [P, 2P, 4P, ...] (classical).
        k is in quantum superposition (LSB first).
        """
        for i in range(k.size):
            pt = powers[i]
            control(k[i], lambda gx=pt[0], gy=pt[1]: ec_point_add(ecp, gx, gy))

    @qfunc
    def main(
        x1:  Output[QNum],
        x2:  Output[QNum],
        ecp: Output[EllipticCurvePoint],
    ) -> None:
        # x1, x2: fractional QNum so measured values are in [0, 1)
        # then x1_r = round(x1 * n)  gives the integer frequency m1
        allocate(var_len, False, var_len, x1)
        allocate(var_len, False, var_len, x2)

        # Initialize ecp = P0 = 2*G
        allocate(ecp)
        ecp.x ^= P0[0]
        ecp.y ^= P0[1]

        # Hadamard superposition on x1, x2
        hadamard_transform(x1)
        hadamard_transform(x2)

        # Oracle: ecp <- P0 + x1*G - x2*Q
        ec_scalar_mult_add(ecp, x1, g_powers)        # add x1*G
        ec_scalar_mult_add(ecp, x2, neg_q_powers)    # add x2*(-Q)

        # Inverse QFT to extract period
        invert(lambda: qft(x1))
        invert(lambda: qft(x2))

    # ------------------------------------------------------------------
    # Synthesize + execute
    # ------------------------------------------------------------------

    qmod = create_model(
        main,
        constraints=Constraints(max_width=300),
        preferences=Preferences(optimization_level=0, timeout_seconds=600),
    )

    with timed("synthesize"):
        qprog = synthesize(qmod)

    with timed("execute"):
        df = execute(qprog).result_value().dataframe

    # ------------------------------------------------------------------
    # Post-processing: peak condition m1*d + m2 ≡ 0 (mod n)
    # => d = -x2_r * x1_r^{-1} mod n,  filter gcd(x1_r, n) == 1
    # x1, x2 are measured as fractions in [0,1); multiply by n to get freq.
    # ------------------------------------------------------------------

    def to_freq(col):
        return df[col].apply(lambda v: round(float(v) * n) % n)

    df["x1_r"] = to_freq("x1")
    df["x2_r"] = to_freq("x2")
    df_valid = df[df["x1_r"].apply(lambda v: math.gcd(int(v), n) == 1)].copy()
    df_valid["d_candidate"] = (
        -df_valid["x2_r"] * df_valid["x1_r"].apply(lambda v: pow(int(v), -1, n))
    ) % n

    play_ending_sound()
    return int(df_valid["d_candidate"].mode()[0])


if __name__ == "__main__":
    for bits in [4]:
        from consts import PARAMS
        expected = PARAMS[bits].d
        print(f"\n--- {bits}-bit (expected d={expected}) ---")
        result = solve(bits)
        print(f"Recovered d={result}, correct={result == expected}")
