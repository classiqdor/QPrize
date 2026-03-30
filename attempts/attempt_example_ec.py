# =============================================================================
# attempt_example_ec — Reference implementation, Method B (EC Oracle)
#
# PURPOSE: Clean, well-commented reference for the genuine EC-oracle approach.
#          Intended as a readable baseline; optimizations go in numbered attempts.
#
# ALGORITHM: Shor's algorithm for ECDLP, EC coordinate encoding (Roetteler 2017).
#
#   The oracle register holds an EC point (x, y) ∈ F_p × F_p.
#   The quantum circuit applies controlled EC point additions using the slope
#   formula mod p. d is never used — not in the circuit, not in precomputation.
#
#   Oracle:   ecp = P0 + x1·G − x2·Q    (EC group arithmetic in F_p)
#
#   After inverse QFT, the measurement peaks satisfy m1 + m2·d ≡ 0 (mod n),
#   so d = −x2_r · x1_r⁻¹ mod n.  (Same post-processing as Method A.)
#
# CLASSICAL PRECOMPUTATION (legitimate):
#   g_powers[i]      = 2^i · G     (successive doublings of G; only G used)
#   neg_q_powers[i]  = −(2^i · Q)  (successive doublings of Q, negate y; only Q used)
#   d is never computed or used.
#
# WHY THIS IS GENUINE ECDLP:
#   Building negq_steps in Method A requires knowing scalar_index(Q) = d.
#   Here, neg_q_powers[i] = −(2^i·Q) requires only Q as an EC point —
#   EC doubling uses only the curve formula (y² = x³ + ax + b mod p), not d.
#
# COST: ~130,000 CX (4-bit). Far too expensive for current simulators/hardware.
#       The cost comes from quantum modular arithmetic (multiply, square, inverse)
#       inside each EC point addition — O(p_bits²) CX per addition.
#
# REFERENCE: Roetteler, Naehrig, Svore, Lauter (2017), Algorithm 1.
# =============================================================================

import math
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from classiq import *
from classiq.qmod.symbolic import subscript

from consts import PARAMS
from utils import timed, play_ending_sound


# -----------------------------------------------------------------------------
# Classical helpers — no d used anywhere
# -----------------------------------------------------------------------------

def ec_double(P: list[int], p: int, a: int) -> list[int]:
    """
    Return 2·P on y² = x³ + ax + b (mod p).
    Uses the tangent-line slope formula: s = (3x² + a) / (2y) mod p.
    """
    x, y = P
    s  = (3 * x * x + a) * pow(2 * y, -1, p) % p
    xr = (s * s - 2 * x) % p
    yr = (s * (x - xr) - y) % p
    return [xr, yr % p]


def ec_negate(P: list[int], p: int) -> list[int]:
    """Return −P: negate the y-coordinate."""
    return [P[0], (p - P[1]) % p]


# -----------------------------------------------------------------------------
# solve(num_bits) — main entry point
# -----------------------------------------------------------------------------

def solve(num_bits: int) -> int:
    """
    Run Shor's ECDLP circuit (EC-oracle variant) for the given bit size.
    Returns the recovered secret d and asserts it equals the expected value.
    """
    params  = PARAMS[num_bits]
    p       = params.p           # field prime
    n       = params.n           # EC group order
    a       = params.a           # curve coefficient a
    G_pt    = list(params.G)     # generator G (public)
    Q_pt    = list(params.Q)     # public key Q = d·G (d is unknown to circuit)
    known_d = params.d           # used ONLY for final correctness check

    var_len = n.bit_length()     # QPE register width
    p_bits  = p.bit_length()     # bits needed to represent a field element
    N       = 1 << var_len       # QPE register size

    # Classical precomputation — only G and Q as EC points; d never touched.
    # P0: starting point for the oracle register (we use 2·G, a non-special point).
    P0    = ec_double(G_pt, p, a)
    neg_Q = ec_negate(Q_pt, p)   # −Q: same x-coordinate, negated y

    print(f"\n[example_ec] {num_bits}-bit | p={p} | n={n} | solving for d...")
    print(f"  Oracle register: {p_bits}-bit (x,y) ∈ F_{p}  |  QPE: {var_len}-bit x1, x2")

    # -------------------------------------------------------------------------
    # Quantum type for an EC point
    # -------------------------------------------------------------------------

    class EllipticCurvePoint(QStruct):
        """A point on the curve: two p_bits-wide unsigned integers."""
        x: QNum[p_bits, False, 0]
        y: QNum[p_bits, False, 0]

    # -------------------------------------------------------------------------
    # Quantum functions (defined inside solve() to capture p, p_bits via closure)
    # -------------------------------------------------------------------------

    @qperm
    def modular_inverse_lookup(
        x:       Const[QNum],
        result:  QNum,
        modulus: int,
    ) -> None:
        """
        |x⟩|0⟩  →  |x⟩|x⁻¹ mod modulus⟩  using a classical lookup table.
        Only feasible for small moduli (modulus < ~50).
        """
        inv_table = lookup_table(
            lambda v: pow(int(v), -1, modulus) if math.gcd(int(v), modulus) == 1 else 0,
            x,
        )
        result ^= subscript(inv_table, x)

    @qperm
    def ec_point_add(
        ecp:   EllipticCurvePoint,
        addend: list[int],          # classical EC point [x, y] to add
        p:     int,
    ) -> None:
        """
        In-place EC point addition: ecp ← ecp + addend  (mod p).

        Implements Roetteler et al. 2017, Algorithm 1 (generic case).
        Assumes ecp ≠ identity, ecp ≠ addend, ecp ≠ −addend (no special cases).
        Slope formula: s = (y1 − Gy) / (x1 − Gx)  mod p
        Result:        x3 = s² − x1 − Gx,  y3 = s·(x1 − x3) − y1

        Steps follow the quantum-reversible implementation: each arithmetic
        operation is either uncomputed (within_apply) or accumulates into a
        fresh ancilla so that the function remains a permutation.
        """
        Gx, Gy = addend[0], addend[1]
        n_bits = p.bit_length()

        slope = QNum();  allocate(n_bits, slope)   # ancilla for the slope s
        t0    = QNum();  allocate(n_bits, t0)       # general-purpose ancilla

        # Step 1 & 2: shift ecp to (x1 − Gx, y1 − Gy) — sets up the slope numerator/denominator
        modular_add_constant_inplace(p, (-Gy) % p, ecp.y)
        modular_add_constant_inplace(p, (-Gx) % p, ecp.x)

        # Step 3: slope = (y1 − Gy) · (x1 − Gx)⁻¹ mod p
        within_apply(
            lambda: modular_inverse_lookup(ecp.x, t0, p),
            lambda: modular_multiply(p, t0, ecp.y, slope),
        )

        # Step 4: zero out ecp.y so it can be reused for y3
        within_apply(
            lambda: modular_multiply(p, slope, ecp.x, t0),
            lambda: inplace_xor(t0, ecp.y),
        )

        # Step 5: ecp.x ← Gx − x3 = Gx − (s² − x1 − Gx) = 3Gx + x1 − s²
        within_apply(
            lambda: modular_square(p, slope, t0),
            lambda: (
                modular_subtract_inplace(p, t0, ecp.x),
                modular_negate_inplace(p, ecp.x),
                modular_add_constant_inplace(p, (3 * Gx) % p, ecp.x),
            ),
        )

        # Step 6: ecp.y ← y3 = slope · (Gx − x3)   [ecp.x currently holds Gx − x3]
        modular_multiply(p, slope, ecp.x, ecp.y)

        # Step 7: uncompute slope ancilla via (Gx − x3)⁻¹
        t1 = QNum()
        within_apply(
            lambda: modular_inverse_lookup(ecp.x, t0, p),
            lambda: within_apply(
                lambda: (allocate(n_bits, t1), modular_multiply(p, t0, ecp.y, t1)),
                lambda: inplace_xor(t1, slope),
            ),
        )
        free(slope)

        # Step 8: restore ecp to final (x3, y3)  [currently holds (Gx−x3, y3)]
        modular_negate_inplace(p, ecp.x)
        modular_add_constant_inplace(p, Gx, ecp.x)
        modular_add_constant_inplace(p, (-Gy) % p, ecp.y)

        free(t0)

    @qperm
    def ec_scalar_mult_add(
        ecp:       EllipticCurvePoint,
        k:         QArray[QBit],
        P_start:   list[int],   # classical EC starting point; doubled per bit internally
        p:         int,
        a:         int,
    ) -> None:
        """
        ecp ← ecp + k·P_start  (EC arithmetic, in-place on ecp).

        For each bit k[i], if k[i]=1, add 2^i·P_start to ecp.
        2^i·P_start is computed classically by doubling — no d involved.
        """
        current = P_start.copy()
        for i in range(k.size):
            control(k[i], lambda cur=current.copy(): ec_point_add(ecp, cur, p))
            if i < k.size - 1:
                current = ec_double(current, p, a)

    # -------------------------------------------------------------------------
    # Three-part main circuit
    # -------------------------------------------------------------------------

    @qfunc
    def prepare_superposition(
        x1: Output[QNum],
        x2: Output[QNum],
    ) -> None:
        """Allocate and Hadamard the two QPE registers."""
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
        """
        Oracle: ecp = P0 + x1·G − x2·Q   (genuine EC arithmetic, d never used).

        Initialises ecp to P0 = 2·G, then:
          - adds x1·G  (controlled additions of G, 2G, 4G, …)
          - adds x2·(−Q)  (controlled additions of −Q, −2Q, −4Q, …)
        """
        allocate(ecp)
        ecp.x ^= P0[0]   # initialise oracle register to P0
        ecp.y ^= P0[1]

        ec_scalar_mult_add(ecp, x1, G_pt, p, a)    # ecp ← P0 + x1·G
        ec_scalar_mult_add(ecp, x2, neg_Q, p, a)   # ecp ← P0 + x1·G − x2·Q

    @qfunc
    def extract_phase(x1: QNum, x2: QNum) -> None:
        """Inverse QFT on both QPE registers to reveal the period."""
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

    # -------------------------------------------------------------------------
    # Synthesize
    # -------------------------------------------------------------------------

    qmod = create_model(
        main,
        constraints=Constraints(max_width=500),
        preferences=Preferences(optimization_level=1, timeout_seconds=3600),
    )
    with timed("Synthesize"):
        qprog = synthesize(qmod)

    ops = qprog.transpiled_circuit.count_ops
    print(f"  Qubits: {qprog.data.width} | Depth: {qprog.transpiled_circuit.depth} "
          f"| CX: {ops.get('cx', 'N/A')}")

    # -------------------------------------------------------------------------
    # Execute + post-process
    # -------------------------------------------------------------------------

    with timed("Execute"):
        res = execute(qprog).result_value()

    df = res.dataframe.sort_values("counts", ascending=False)

    # Scale raw QPE fractions back to frequency integers in Z_n.
    # x measurements are fractions in [0,1); multiply by n to get m ∈ Z_n.
    df["x1_r"] = df["x1"].apply(lambda v: round(float(v) * n) % n)
    df["x2_r"] = df["x2"].apply(lambda v: round(float(v) * n) % n)

    # Keep only rows where x1_r is invertible mod n
    df = df[df["x1_r"].apply(lambda v: math.gcd(int(v), n) == 1)].copy()

    # Peak condition: m1 + m2·d ≡ 0 (mod n)  ⟹  d = −x2_r · x1_r⁻¹ mod n
    df["d_candidate"] = (
        -df["x2_r"] * df["x1_r"].apply(lambda v: pow(int(v), -1, n))
    ) % n

    recovered = int(df["d_candidate"].mode()[0])
    match = recovered == known_d
    print(f"  Recovered d={recovered}, expected d={known_d} → {'✅' if match else '❌'}")
    assert match, f"MISMATCH: got {recovered}, expected {known_d}"

    play_ending_sound()
    return recovered


if __name__ == "__main__":
    bits = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    solve(bits)
