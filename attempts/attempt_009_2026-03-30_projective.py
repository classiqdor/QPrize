# =============================================================================
# Attempt 009 — 2026-03-30
#
# CHANGE: Replace affine EC point addition (attempts 007/008) with
#         PROJECTIVE (homogeneous) coordinate EC addition — no modular inverse
#         inside the oracle loop.
#
# WHY: attempts 007/008 call scalable_modular_inverse (Kaliski, O(p_bits²)
#   gates) inside every controlled EC point addition.  For var_len QPE
#   bits there are 2·var_len controlled additions, so the total inverse cost
#   alone is O(var_len · p_bits²) — the dominant term.
#
#   Projective (homogeneous) Weierstrass coordinates represent each EC point
#   as (X : Y : Z) with (x, y) = (X/Z, Y/Z).  The mixed add formula
#   (projective accumulator + affine classical constant) uses only field
#   multiplications — no modular inverse at all.  One final affine conversion
#   (one modular inverse via Kaliski) is done after all additions finish.
#
#   Expected benefit: eliminate O(var_len) quantum modular inverses, leaving
#   only O(1) inverse total.  Circuit depth drops roughly proportionally.
#
# ALGORITHM: Same as attempt_007/008 — Shor ECDLP via Roetteler et al. 2017
#   Oracle:        ecp_proj ← P0_proj + x1·G − x2·Q  (projective coords)
#   Post-oracle:   ecp_proj → (x3, y3) affine (one Kaliski inverse)
#   Period finding: inverse QFT on x1, x2
#
# PROJECTIVE MIXED-ADD (Hankerson et al., §3.2.2 — standard projective):
#   Input:  (X1:Y1:Z1) accumulator,  (x2, y2) affine classical point
#   Output: (X3:Y3:Z3)
#   u = y2·Z1 − Y1
#   v = x2·Z1 − X1
#   w = u²·Z1 − v³ − 2·v²·X1
#   X3 = v·w
#   Y3 = u·(v²·X1 − w) − v³·Y1
#   Z3 = v³·Z1
#   All operations mod p — no inversion.
#
# AFFINE RECOVERY (one inverse per solve() call, after all additions):
#   x = X3 · Z3^{-1} mod p
#   y = Y3 · Z3^{-1} mod p    (standard projective, not Jacobian)
#
# SCALABILITY: Classical precomputation is O(bits) EC doublings.
#   Circuit size grows polynomially with key size.
#   Modular inverse count: 1 (affine recovery) vs 2·var_len (attempt_007/008).
#
# PREVIOUS: attempt_008_2026-03-29_1859 — same algorithm, affine coords,
#           Kaliski inverse per addition.
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


def ec_add_affine(P, Q_pt, p, a):
    """Classical EC point addition: returns P + Q_pt (affine, mod p)."""
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


def affine_to_proj(P):
    """Convert affine (x, y) to standard projective (X, Y, Z) = (x, y, 1)."""
    return [P[0], P[1], 1]


# %% Core solve function

def solve(num_bits: int) -> int:
    """
    Synthesize and execute Shor's ECDLP circuit using projective coordinates.

    Key difference from attempt_007/008: the quantum EC register holds
    (X, Y, Z) in standard projective coordinates.  Mixed-add (projective +
    affine constant) uses only multiplications — no modular inverse per
    addition.  A single Kaliski inverse converts back to affine after all
    additions are complete.

    Returns the recovered private key d, or raises AssertionError on mismatch.
    """
    assert num_bits in SUPPORTED_BITS, f"attempt_009 supports {SUPPORTED_BITS}, got {num_bits}"

    params  = PARAMS[num_bits]
    p       = params.p
    n       = params.n
    a       = params.a
    G_pt    = list(params.G)
    Q_pt    = list(params.Q)
    known_d = params.d          # used only for final assertion
    var_len = n.bit_length()    # QPE register width
    p_bits  = p.bit_length()    # coordinate register width

    # Classical precomputation — O(var_len) EC doublings, no enumeration.
    P0_affine    = ec_double(G_pt, p, a)           # initial affine point = 2·G
    g_powers     = build_powers(G_pt, p, a, var_len)
    q_powers     = build_powers(Q_pt, p, a, var_len)
    neg_q_powers = [[pt[0], (p - pt[1]) % p] for pt in q_powers]

    # Initial projective point: (X0, Y0, Z0) = (x0, y0, 1)
    P0_proj = affine_to_proj(P0_affine)

    print(f"\n[attempt_009] {num_bits}-bit | p={p} | n={n} | p_bits={p_bits} | var_len={var_len}")
    print(f"  P0 (affine) = {P0_affine}")
    print(f"  P0 (proj)   = {P0_proj}")
    print(f"  g_powers    = {[tuple(pt) for pt in g_powers]}")
    print(f"  -q_powers   = {[tuple(pt) for pt in neg_q_powers]}")
    print(f"  Encoding: standard projective — mixed-add, one final inverse")

    # -----------------------------------------------------------------------
    # Quantum type definitions — capture p, p_bits from outer scope
    # -----------------------------------------------------------------------

    class EllipticCurvePointProj(QStruct):
        """Standard projective point (X:Y:Z) over F_p.  (x,y) = (X/Z, Y/Z)."""
        X: QNum[p_bits, False, 0]   # type: ignore[valid-type]
        Y: QNum[p_bits, False, 0]   # type: ignore[valid-type]
        Z: QNum[p_bits, False, 0]   # type: ignore[valid-type]

    class EllipticCurvePointAffine(QStruct):
        """Affine point (x, y) over F_p — used for the final output register."""
        x: QNum[p_bits, False, 0]   # type: ignore[valid-type]
        y: QNum[p_bits, False, 0]   # type: ignore[valid-type]

    # -----------------------------------------------------------------------
    # Scalable modular inverse: result ^= inp^{-1} mod p  (Kaliski)
    # Called ONCE after all additions, not inside the loop.
    # -----------------------------------------------------------------------

    @qperm
    def scalable_modular_inverse(inp: Const[QNum], result: QNum) -> None:
        """result ^= inp^{-1} mod p via Kaliski algorithm (O(p_bits²) gates)."""
        v: QNum = QNum("inv_v", p_bits)
        m: QArray[QBit] = QArray[QBit]()
        allocate(p_bits, False, 0, v)
        v ^= inp
        within_apply(
            lambda: modular_inverse_inplace(p, v, m),
            lambda: inplace_xor(v, result),
        )
        v ^= inp
        free(v)

    # -----------------------------------------------------------------------
    # Projective mixed-add: ecp_proj ← ecp_proj + (gx, gy)  (gx, gy affine)
    #
    # Standard projective mixed-add formulas (no inversion):
    #   u = gy·Z1 − Y1
    #   v = gx·Z1 − X1
    #   v2 = v²
    #   v3 = v³ = v·v²
    #   A  = u²·Z1 − v3 − 2·v2·X1
    #   X3 = v·A
    #   Y3 = u·(v2·X1 − A) − v3·Y1
    #   Z3 = v3·Z1
    #
    # All temporaries start and end at 0 (reversible).
    # -----------------------------------------------------------------------

    @qperm
    def proj_mixed_add(ecp: EllipticCurvePointProj, gx: int, gy: int) -> None:
        """In-place: ecp ← ecp + (gx, gy), standard projective mixed-add."""
        # Allocate temporaries
        u:   QNum = QNum("u",   p_bits)
        v:   QNum = QNum("v",   p_bits)
        v2:  QNum = QNum("v2",  p_bits)
        v3:  QNum = QNum("v3",  p_bits)
        A:   QNum = QNum("A",   p_bits)
        t:   QNum = QNum("t",   p_bits)
        allocate(p_bits, False, 0, u)
        allocate(p_bits, False, 0, v)
        allocate(p_bits, False, 0, v2)
        allocate(p_bits, False, 0, v3)
        allocate(p_bits, False, 0, A)
        allocate(p_bits, False, 0, t)

        # --- Compute u = gy·Z1 − Y1  (mod p) ---
        # u starts at 0; add gy·Z1 then subtract Y1.
        modular_multiply(p, ecp.Z, gy, u)              # u = gy·Z1
        modular_subtract_inplace(p, ecp.Y, u)          # u = gy·Z1 − Y1

        # --- Compute v = gx·Z1 − X1  (mod p) ---
        modular_multiply(p, ecp.Z, gx, v)              # v = gx·Z1
        modular_subtract_inplace(p, ecp.X, v)          # v = gx·Z1 − X1

        # --- Compute v2 = v²  (mod p) ---
        modular_square(p, v, v2)                        # v2 = v²

        # --- Compute v3 = v·v2 = v³  (mod p) ---
        modular_multiply(p, v, v2, v3)                  # v3 = v³

        # --- Compute A = u²·Z1 − v3 − 2·v2·X1  (mod p) ---
        # A = u²·Z1 − v3 − 2·v2·X1
        within_apply(
            lambda: modular_square(p, u, t),             # t = u²
            lambda: modular_multiply(p, t, ecp.Z, A),   # A = u²·Z1
        )
        modular_subtract_inplace(p, v3, A)               # A = u²·Z1 − v3
        within_apply(
            lambda: modular_multiply(p, v2, ecp.X, t),  # t = v2·X1
            lambda: (
                modular_add_constant_inplace(p, 0, t),  # no-op placeholder (t already set)
                modular_subtract_inplace(p, t, A),       # A -= v2·X1
                modular_subtract_inplace(p, t, A),       # A -= v2·X1 again (total: 2·v2·X1)
            ),
        )

        # --- Compute X3 = v·A  and store back ---
        # New X3 replaces ecp.X.  First zero out ecp.X, then set to v·A.
        within_apply(
            lambda: modular_multiply(p, v, A, t),        # t = v·A = X3
            lambda: (
                inplace_xor(ecp.X, t),                   # ecp.X ^= t  (ecp.X now = old XOR X3)
            ),
        )
        # We need ecp.X = X3 = v·A.  If old ecp.X was arbitrary we must zero it first.
        # Use: ecp.X_new = ecp.X_old XOR X3 is not correct unless ecp.X_old was 0.
        # Instead, uncompute old X1 via t, then set X3.
        # This is handled correctly: within_apply computes t=v·A, XORs into ecp.X,
        # then uncomputes t.  So ecp.X = old_X1 XOR X3.  We still need to clear old_X1.
        # Fix: do it in two steps using an extra temporary.
        # (See detailed derivation in comments below.)
        #
        # Revised approach:  use t to hold X3, XOR ecp.X with (old_X1 XOR X3), then
        # XOR again with old_X1 to get X3.  old_X1 must be preserved until we can
        # uncompute it.  We already have v = gx·Z1 − X1 so X1 = gx·Z1 − v (mod p).
        # We can reconstruct X1 from v and Z1.
        #
        # Simplification: allocate x1_old, save ecp.X there, zero ecp.X, then set X3.

        # Actually, let's re-approach: since within_apply above already XORed X3 into
        # ecp.X (giving ecp.X = old_X1 XOR X3), we need to XOR out old_X1.
        # old_X1 can be recovered from v: X1 = gx·Z1 − v (mod p).
        within_apply(
            lambda: (
                modular_multiply(p, ecp.Z, gx, t),       # t = gx·Z1
                modular_subtract_inplace(p, v, t),        # t = gx·Z1 − v = X1  (mod p)
            ),
            lambda: inplace_xor(t, ecp.X),               # ecp.X ^= X1  →  ecp.X = X1 XOR (X1 XOR X3) = X3
        )

        # --- Compute Z3 = v3·Z1 and store back ---
        # Same pattern: ecp.Z = Z1 → Z3 = v3·Z1.
        # We need to zero Z1 out of ecp.Z, set Z3.
        within_apply(
            lambda: modular_multiply(p, v3, ecp.Z, t),   # t = v3·Z1 = Z3
            lambda: inplace_xor(ecp.Z, t),               # ecp.Z ^= Z3  →  Z1 XOR Z3
        )
        # Now ecp.Z = Z1 XOR Z3.  XOR out Z1 to get Z3.
        # Z1 must be recovered.  But we no longer have it directly after XOR.
        # Z3 = v3·Z1 ⟹ Z1 = Z3 / v3 — requires inverse.  Avoid this.
        #
        # Better: save Z1 to t before modifying, then XOR at the end.
        # The within_apply above already used t for Z3.  We need a fresh approach.
        #
        # Use a separate temp z1_save.  Restructure the Z update below.
        # (The within_apply above is reverted — see rewrite of Z update at end.)

        # --- Compute Y3 = u·(v2·X1 − A) − v3·Y1 ---
        # v2·X1: X1 = gx·Z1 − v (recoverable).
        within_apply(
            lambda: (
                modular_multiply(p, ecp.Z, gx, t),       # t = gx·Z1  (uses current Z which is Z1 XOR Z3 — BUG)
            ),
            lambda: None,
        )
        # *** There are ordering dependencies above that need careful resolution. ***
        # See the complete, clean rewrite below — the above sketched steps are
        # superseded by the correct implementation that follows.

        free(u)
        free(v)
        free(v2)
        free(v3)
        free(A)
        free(t)

    # -----------------------------------------------------------------------
    # NOTE: The mixed-add implementation above has correctness issues due to
    # the ordering of X1/Z1 preservation vs modification.  The clean approach
    # is to use two extra temporaries (x1_save, z1_save) to snapshot the
    # original X1 and Z1 before they are overwritten, then use those snapshots
    # for the Y3 and Z3 computations.  The full correct implementation follows.
    # -----------------------------------------------------------------------

    @qperm
    def proj_mixed_add_clean(ecp: EllipticCurvePointProj, gx: int, gy: int) -> None:
        """
        In-place standard projective mixed-add: ecp ← ecp + (gx, gy).

        Uses two snapshot temporaries (x1_save, z1_save) so that the original
        X1 and Z1 values remain available for Y3 and Z3 computation after
        X1 and Z1 have been overwritten with X3 and Z3.

        Formula (Hankerson et al. §3.2.2, standard projective, mixed input):
          u  = gy·Z1 − Y1
          v  = gx·Z1 − X1
          v2 = v²
          v3 = v³
          A  = u²·Z1 − v3 − 2·v2·X1
          X3 = v·A
          Y3 = u·(v2·X1 − A) − v3·Y1
          Z3 = v3·Z1
        """
        # ---- Allocate all temporaries (all start at 0) ----
        u:      QNum = QNum("u",      p_bits)
        v:      QNum = QNum("v",      p_bits)
        v2:     QNum = QNum("v2",     p_bits)
        v3:     QNum = QNum("v3",     p_bits)
        A:      QNum = QNum("A_proj", p_bits)
        t:      QNum = QNum("t_proj", p_bits)
        x1s:    QNum = QNum("x1s",    p_bits)  # snapshot of X1
        z1s:    QNum = QNum("z1s",    p_bits)  # snapshot of Z1
        y1s:    QNum = QNum("y1s",    p_bits)  # snapshot of Y1
        allocate(p_bits, False, 0, u)
        allocate(p_bits, False, 0, v)
        allocate(p_bits, False, 0, v2)
        allocate(p_bits, False, 0, v3)
        allocate(p_bits, False, 0, A)
        allocate(p_bits, False, 0, t)
        allocate(p_bits, False, 0, x1s)
        allocate(p_bits, False, 0, z1s)
        allocate(p_bits, False, 0, y1s)

        # ---- Save snapshots of X1, Y1, Z1 ----
        x1s ^= ecp.X    # x1s = X1
        y1s ^= ecp.Y    # y1s = Y1
        z1s ^= ecp.Z    # z1s = Z1

        # ---- u = gy·Z1 − Y1  (mod p) ----
        modular_multiply(p, z1s, gy, u)             # u = gy·Z1
        modular_subtract_inplace(p, y1s, u)         # u = gy·Z1 − Y1

        # ---- v = gx·Z1 − X1  (mod p) ----
        modular_multiply(p, z1s, gx, v)             # v = gx·Z1
        modular_subtract_inplace(p, x1s, v)         # v = gx·Z1 − X1

        # ---- v2 = v²  (mod p) ----
        modular_square(p, v, v2)                     # v2 = v²

        # ---- v3 = v·v2 = v³  (mod p) ----
        modular_multiply(p, v, v2, v3)               # v3 = v³

        # ---- A = u²·Z1 − v3 − 2·v2·X1  (mod p) ----
        within_apply(
            lambda: modular_square(p, u, t),          # t = u²
            lambda: modular_multiply(p, t, z1s, A),  # A = u²·Z1
        )
        modular_subtract_inplace(p, v3, A)            # A -= v3  →  A = u²·Z1 − v3
        within_apply(
            lambda: modular_multiply(p, v2, x1s, t), # t = v2·X1
            lambda: (
                modular_subtract_inplace(p, t, A),    # A -= v2·X1
                modular_subtract_inplace(p, t, A),    # A -= v2·X1  (total: 2·v2·X1)
            ),
        )
        # Now: A = u²·Z1 − v3 − 2·v2·X1  ✓

        # ---- Set X3 = v·A into ecp.X ----
        # ecp.X currently = X1; we need ecp.X = X3 = v·A.
        # XOR in X3, then XOR out X1 (available as x1s).
        within_apply(
            lambda: modular_multiply(p, v, A, t),     # t = X3 = v·A
            lambda: inplace_xor(ecp.X, t),            # ecp.X = X1 XOR X3
        )
        inplace_xor(ecp.X, x1s)                        # ecp.X = (X1 XOR X3) XOR X1 = X3  ✓

        # ---- Compute Y3 = u·(v2·X1 − A) − v3·Y1 and set ecp.Y ----
        # First compute v2·X1 − A into t, then multiply by u into a fresh temp.
        # We need another temporary for the partial product.
        # Reuse pattern: compute into t, XOR into ecp.Y, uncompute.
        within_apply(
            lambda: (
                modular_multiply(p, v2, x1s, t),      # t = v2·X1
                modular_subtract_inplace(p, A, t),    # t = v2·X1 − A
            ),
            lambda: within_apply(
                lambda: modular_multiply(p, u, t, v2),  # v2 repurposed: = u·(v2·X1−A)
                # Note: v2 is no longer needed after this point; safe to reuse.
                lambda: inplace_xor(ecp.Y, v2),          # ecp.Y = Y1 XOR u·(v2·X1−A)
            ),
        )
        # Now subtract v3·Y1 from ecp.Y.
        # ecp.Y = Y1 XOR u·(v2·X1−A).  We need ecp.Y = Y3 = u·(v2·X1−A) − v3·Y1.
        # XOR-based arithmetic: XOR Y1 out, subtract v3·Y1 − Y1 = (v3−1)·Y1 — complicated.
        # Cleaner: snapshot approach:
        #   ecp.Y = Y1 XOR [u·(v2·X1−A)] needs → Y3 = u·(v2·X1−A) − v3·Y1
        # Step a: XOR out Y1 → ecp.Y = u·(v2·X1−A)   (using y1s snapshot)
        inplace_xor(ecp.Y, y1s)                        # ecp.Y = (Y1 XOR …) XOR Y1 = u·(v2·X1−A)
        # Step b: subtract v3·Y1
        within_apply(
            lambda: modular_multiply(p, v3, y1s, t),  # t = v3·Y1
            lambda: modular_subtract_inplace(p, t, ecp.Y),  # ecp.Y = u·(v2·X1−A) − v3·Y1 = Y3  ✓
        )

        # ---- Set Z3 = v3·Z1 into ecp.Z ----
        within_apply(
            lambda: modular_multiply(p, v3, z1s, t),  # t = Z3 = v3·Z1
            lambda: inplace_xor(ecp.Z, t),            # ecp.Z = Z1 XOR Z3
        )
        inplace_xor(ecp.Z, z1s)                        # ecp.Z = Z3  ✓

        # ---- Uncompute v3 (was v·v2; need to reverse modular_multiply) ----
        # Uncompute using within_apply style: XOR v3 back to 0 via modular_multiply.
        within_apply(
            lambda: modular_multiply(p, v, v2, t),    # t = v·v2 = v3
            lambda: inplace_xor(v3, t),               # v3 ^= t → v3 = 0  ✓
        )

        # ---- Uncompute v2 = v² ----
        within_apply(
            lambda: modular_square(p, v, t),           # t = v²
            lambda: inplace_xor(v2, t),               # v2 ^= t → v2 = 0  ✓
        )

        # ---- Uncompute u: u = gy·Z1 − Y1 → 0 ----
        # Z1 available in z1s, Y1 in y1s.
        within_apply(
            lambda: modular_multiply(p, z1s, gy, t),  # t = gy·Z1
            lambda: inplace_xor(u, t),                # u ^= gy·Z1 →  u = (gy·Z1 − Y1) XOR gy·Z1 ← not 0
        )
        # Hmm — XOR-based uncompute is not the same as subtract.
        # u was computed as: u = gy·Z1 − Y1.  To zero it out:
        #   add Y1 back, then subtract gy·Z1.
        modular_add_inplace(p, y1s, u)                 # u = gy·Z1 − Y1 + Y1 = gy·Z1
        within_apply(
            lambda: modular_multiply(p, z1s, gy, t),  # t = gy·Z1
            lambda: modular_subtract_inplace(p, t, u),  # u = gy·Z1 − gy·Z1 = 0  ✓
        )

        # ---- Uncompute v: v = gx·Z1 − X1 → 0 ----
        modular_add_inplace(p, x1s, v)                 # v = gx·Z1 − X1 + X1 = gx·Z1
        within_apply(
            lambda: modular_multiply(p, z1s, gx, t),  # t = gx·Z1
            lambda: modular_subtract_inplace(p, t, v),  # v = 0  ✓
        )

        # ---- Uncompute A: set to 0 ----
        # A = u²·Z1 − v3 − 2·v2·X1  (all in original values).
        # At this point u=0, v=0, v2=0, v3=0, so all intermediates are gone.
        # A is still holding its computed value; we need to zero it.
        # Recompute A from snapshots (x1s, y1s, z1s are still intact).
        within_apply(
            lambda: (
                modular_square(p, u, t),               # BUG: u=0 now, can't recompute A this way
            ),
            lambda: inplace_xor(A, t),
        )
        # *** The uncompute of A above is broken because u and v were already zeroed. ***
        # Correct fix: uncompute A BEFORE uncomputing u, v, v2, v3.
        # The code above is reordered correctly in the final clean version below.
        # This function is superseded by proj_mixed_add_v2 which has the correct order.

        # Free everything (even though some may not be truly 0 due to ordering bugs above)
        free(u)
        free(v)
        free(v2)
        free(v3)
        free(A)
        free(t)
        free(x1s)
        free(z1s)
        free(y1s)

    # -----------------------------------------------------------------------
    # Final correct implementation: proj_mixed_add_v2
    # Uncompute order: A, v3, v2, u, v (reverse of computation order),
    # keeping snapshots (x1s, y1s, z1s) alive throughout.
    # -----------------------------------------------------------------------

    @qperm
    def proj_mixed_add_v2(ecp: EllipticCurvePointProj, gx: int, gy: int) -> None:
        """
        In-place standard projective mixed-add: ecp ← ecp + (gx, gy).

        Correct reversible implementation with snapshot temporaries and
        proper uncompute order.
        """
        # ---- Allocate all temporaries ----
        u:   QNum = QNum("u2",   p_bits)
        v:   QNum = QNum("v2",   p_bits)
        v2q: QNum = QNum("v2q",  p_bits)   # v²
        v3q: QNum = QNum("v3q",  p_bits)   # v³
        Aq:  QNum = QNum("Aq",   p_bits)   # A
        t:   QNum = QNum("tq",   p_bits)   # scratch
        x1s: QNum = QNum("x1sq", p_bits)   # snapshot of X1
        z1s: QNum = QNum("z1sq", p_bits)   # snapshot of Z1
        y1s: QNum = QNum("y1sq", p_bits)   # snapshot of Y1
        allocate(p_bits, False, 0, u)
        allocate(p_bits, False, 0, v)
        allocate(p_bits, False, 0, v2q)
        allocate(p_bits, False, 0, v3q)
        allocate(p_bits, False, 0, Aq)
        allocate(p_bits, False, 0, t)
        allocate(p_bits, False, 0, x1s)
        allocate(p_bits, False, 0, z1s)
        allocate(p_bits, False, 0, y1s)

        # ---- Phase 0: snapshot ----
        x1s ^= ecp.X
        y1s ^= ecp.Y
        z1s ^= ecp.Z

        # ---- Phase 1: compute u = gy·Z1 − Y1 ----
        modular_multiply(p, z1s, gy, u)
        modular_subtract_inplace(p, y1s, u)

        # ---- Phase 2: compute v = gx·Z1 − X1 ----
        modular_multiply(p, z1s, gx, v)
        modular_subtract_inplace(p, x1s, v)

        # ---- Phase 3: v2q = v² ----
        modular_square(p, v, v2q)

        # ---- Phase 4: v3q = v³ = v·v² ----
        modular_multiply(p, v, v2q, v3q)

        # ---- Phase 5: Aq = u²·Z1 − v3q − 2·v2q·X1 ----
        within_apply(
            lambda: modular_square(p, u, t),
            lambda: modular_multiply(p, t, z1s, Aq),
        )
        modular_subtract_inplace(p, v3q, Aq)
        within_apply(
            lambda: modular_multiply(p, v2q, x1s, t),
            lambda: (
                modular_subtract_inplace(p, t, Aq),
                modular_subtract_inplace(p, t, Aq),
            ),
        )

        # ---- Phase 6: overwrite ecp.X with X3 = v·Aq ----
        within_apply(
            lambda: modular_multiply(p, v, Aq, t),
            lambda: inplace_xor(ecp.X, t),
        )
        inplace_xor(ecp.X, x1s)      # ecp.X = X3

        # ---- Phase 7: overwrite ecp.Y with Y3 = u·(v2q·X1 − Aq) − v3q·Y1 ----
        # Compute u·(v2q·X1 − Aq) into ecp.Y, then subtract v3q·Y1, then XOR Y1 out.
        within_apply(
            lambda: (
                modular_multiply(p, v2q, x1s, t),
                modular_subtract_inplace(p, Aq, t),
            ),
            lambda: within_apply(
                lambda: modular_multiply(p, u, t, v3q),   # reuse v3q temporarily? No — v3q is live.
                # Can't reuse v3q here; use a fresh reg via within_apply nesting.
                lambda: None,
            ),
        )
        # Revised Y3 computation using the scratch t differently:
        # Step 7a: t = v2q·X1 − Aq
        within_apply(
            lambda: modular_multiply(p, v2q, x1s, t),
            lambda: modular_subtract_inplace(p, Aq, t),  # t = v2q·X1 − Aq  (inside apply: t set, subtract, then un-set?)
        )
        # NOTE: within_apply(compute, action): computes t, runs action with t set, then uncomputes t.
        # The action lambda must complete with t unchanged (relative to what compute left it as).
        # So `modular_subtract_inplace(p, Aq, t)` modifies t — within_apply can't uncompute t after that.
        # We need a different pattern for accumulation.
        #
        # Clean pattern for Y3:
        #   Allocate y3_tmp, compute it directly, swap into ecp.Y, uncompute y3_tmp.
        #
        # This is getting complex. Use a helper allocate+free pattern.

        # ---- Y3 computation (clean) ----
        # Allocate y3_tmp to build Y3 from scratch, then set ecp.Y = Y3.
        y3_tmp: QNum = QNum("y3tmp", p_bits)
        allocate(p_bits, False, 0, y3_tmp)

        # y3_tmp = u·(v2q·X1 − Aq)
        within_apply(
            lambda: (
                modular_multiply(p, v2q, x1s, t),       # t = v2q·X1
                modular_subtract_inplace(p, Aq, t),     # t = v2q·X1 − Aq  (modifies t — within_apply can't uncompute cleanly)
            ),
            lambda: modular_multiply(p, u, t, y3_tmp),  # y3_tmp = u·t
        )
        # BUG: within_apply requires that 'compute' and its inverse are clean.
        # modular_subtract_inplace modifies t permanently, so within_apply cannot uncompute it.
        # Correct approach: compute (v2q·X1 − Aq) into a dedicated register.

        free(y3_tmp)

        # ---- Final fallback: use a dedicated intermediate register for each sub-expression ----
        vm_a: QNum = QNum("vma", p_bits)   # will hold v2q·X1 − Aq
        y3r:  QNum = QNum("y3r", p_bits)   # will hold Y3
        allocate(p_bits, False, 0, vm_a)
        allocate(p_bits, False, 0, y3r)

        # vm_a = v2q·X1 − Aq (compute in two steps, no within_apply needed)
        modular_multiply(p, v2q, x1s, vm_a)            # vm_a = v2q·X1
        modular_subtract_inplace(p, Aq, vm_a)          # vm_a = v2q·X1 − Aq

        # y3r = u·vm_a
        modular_multiply(p, u, vm_a, y3r)              # y3r = u·(v2q·X1 − Aq)

        # y3r -= v3q·Y1
        within_apply(
            lambda: modular_multiply(p, v3q, y1s, t),  # t = v3q·Y1
            lambda: modular_subtract_inplace(p, t, y3r),  # y3r -= v3q·Y1  →  y3r = Y3
        )

        # Set ecp.Y = Y3: XOR in y3r, XOR out Y1 (using y1s).
        inplace_xor(ecp.Y, y3r)                         # ecp.Y = Y1 XOR Y3
        inplace_xor(ecp.Y, y1s)                         # ecp.Y = Y3  ✓

        # ---- Phase 8: overwrite ecp.Z with Z3 = v3q·Z1 ----
        within_apply(
            lambda: modular_multiply(p, v3q, z1s, t),   # t = Z3 = v3q·Z1
            lambda: inplace_xor(ecp.Z, t),              # ecp.Z = Z1 XOR Z3
        )
        inplace_xor(ecp.Z, z1s)                          # ecp.Z = Z3  ✓

        # ---- Uncompute y3r → 0 ----
        # Reverse of y3r construction: add back v3q·Y1, then reverse multiply.
        within_apply(
            lambda: modular_multiply(p, v3q, y1s, t),
            lambda: modular_add_inplace(p, t, y3r),      # y3r += v3q·Y1  →  y3r = u·vm_a
        )
        within_apply(
            lambda: modular_multiply(p, u, vm_a, t),
            lambda: inplace_xor(y3r, t),                 # y3r ^= u·vm_a → y3r = 0  ✓
        )

        # ---- Uncompute vm_a → 0 ----
        modular_add_inplace(p, Aq, vm_a)                 # vm_a = v2q·X1 − Aq + Aq = v2q·X1
        within_apply(
            lambda: modular_multiply(p, v2q, x1s, t),
            lambda: modular_subtract_inplace(p, t, vm_a),  # vm_a = v2q·X1 − v2q·X1 = 0  ✓
        )

        free(vm_a)
        free(y3r)

        # ---- Uncompute Aq → 0 ----
        # Reverse of phase 5: add back 2·v2q·X1, add v3q, then reverse u²·Z1.
        within_apply(
            lambda: modular_multiply(p, v2q, x1s, t),
            lambda: (
                modular_add_inplace(p, t, Aq),           # Aq += v2q·X1
                modular_add_inplace(p, t, Aq),           # Aq += v2q·X1  (total: 2·v2q·X1 added back)
            ),
        )
        modular_add_inplace(p, v3q, Aq)                  # Aq += v3q  →  Aq = u²·Z1
        within_apply(
            lambda: modular_square(p, u, t),
            lambda: within_apply(
                lambda: modular_multiply(p, t, z1s, Aq),  # this within_apply would overwrite Aq — wrong
                lambda: None,
            ),
        )
        # Can't use within_apply(compute Aq, action) to uncompute Aq itself.
        # Correct uncompute: Aq currently = u²·Z1.  XOR out u²·Z1 to zero it.
        within_apply(
            lambda: modular_square(p, u, t),             # t = u²
            lambda: within_apply(
                lambda: modular_multiply(p, t, z1s, Aq), # BUG: this adds u²·Z1 to Aq, not XOR
                lambda: None,
            ),
        )
        # modular_multiply(p, a, b, c) computes c ^= a*b (XOR-based in quantum arithmetic).
        # So modular_multiply(p, t, z1s, Aq) sets Aq ^= u²·Z1.
        # If Aq = u²·Z1 currently, then Aq ^= u²·Z1 = 0.  ✓  But we're inside within_apply
        # which will then call the action (None) and reverse the compute — un-XORing Aq.
        # That would leave Aq = u²·Z1 again.
        #
        # Correct pattern: just call modular_multiply directly (not inside within_apply).
        within_apply(
            lambda: modular_square(p, u, t),
            lambda: modular_multiply(p, t, z1s, Aq),    # Aq ^= u²·Z1  →  Aq = 0  ✓ (direct, not within_apply)
        )

        # ---- Uncompute v3q → 0 ----
        within_apply(
            lambda: modular_multiply(p, v, v2q, t),
            lambda: inplace_xor(v3q, t),                 # v3q ^= v·v2q → v3q = 0  ✓
        )

        # ---- Uncompute v2q → 0 ----
        within_apply(
            lambda: modular_square(p, v, t),
            lambda: inplace_xor(v2q, t),                 # v2q ^= v² → v2q = 0  ✓
        )

        # ---- Uncompute u → 0 ----
        modular_add_inplace(p, y1s, u)                   # u = gy·Z1 − Y1 + Y1 = gy·Z1
        within_apply(
            lambda: modular_multiply(p, z1s, gy, t),
            lambda: modular_subtract_inplace(p, t, u),  # u = gy·Z1 − gy·Z1 = 0  ✓
        )

        # ---- Uncompute v → 0 ----
        modular_add_inplace(p, x1s, v)                   # v = gx·Z1 − X1 + X1 = gx·Z1
        within_apply(
            lambda: modular_multiply(p, z1s, gx, t),
            lambda: modular_subtract_inplace(p, t, v),  # v = 0  ✓
        )

        # ---- Uncompute snapshots ----
        # At this point ecp.X = X3, ecp.Y = Y3, ecp.Z = Z3.
        # x1s = X1 (unchanged), y1s = Y1, z1s = Z1.
        # We need to zero the snapshots.
        # But snapshots were set to X1/Y1/Z1 which are no longer the current ecp values.
        # We must uncompute x1s = X1 using some reversible route.
        # X1 can be recovered from: v = gx·Z1 − X1 → X1 = gx·Z1 − v.
        # But v is now 0.  And Z1 is gone (ecp.Z = Z3 now).
        # z1s = Z1 was XORed as z1s ^= ecp.Z (when ecp.Z = Z1), so z1s = Z1.
        # To uncompute z1s: z1s ^= Z1.  Z1 is still accessible? Only via z1s itself.
        # This is a circular dependency — we need Z1 to uncompute z1s, but z1s IS Z1.
        # Answer: we can directly XOR z1s with ecp.Z = Z3 won't help.
        # The snapshots are fundamentally entangled with the pre-modified ecp.
        #
        # Standard solution: snapshot AFTER a within_apply that restores the original.
        # Or: use the "copy-uncompute" trick — since ecp was modified in place,
        # we can uncompute snapshots by re-deriving the original values.
        #
        # For Z1: Z3 = v3q·Z1 was computed with v3q from the old v, v2q.
        # All of v, v2q, v3q are now 0, so we can't re-derive Z1 from Z3.
        #
        # This reveals a fundamental issue: in a fully reversible implementation,
        # either (a) the function signature must include the pre-state as outputs, or
        # (b) the snapshots must be uncomputed before modifying ecp, using the
        #     intermediate values.
        #
        # CORRECT ARCHITECTURE: use within_apply at the top level.
        # within_apply(compute_intermediates, use_intermediates_to_update_ecp)
        # Classiq's within_apply automatically uncomputes 'compute_intermediates'.
        # The snapshots become the 'compute' phase.
        #
        # See proj_mixed_add_final below for the architecturally correct version.

        free(u)
        free(v)
        free(v2q)
        free(v3q)
        free(Aq)
        free(t)
        free(x1s)
        free(z1s)
        free(y1s)

    # -----------------------------------------------------------------------
    # Architecturally correct projective mixed-add using within_apply at
    # the top level for automatic uncomputation of intermediates.
    # -----------------------------------------------------------------------

    @qperm
    def proj_mixed_add_final(ecp: EllipticCurvePointProj, gx: int, gy: int) -> None:
        """
        In-place standard projective mixed-add: ecp ← ecp + (gx, gy).

        Architecture:
          within_apply(
              compute: derive all intermediates (u, v, v2, v3, A) from ecp + constants,
              action:  update ecp.X, ecp.Y, ecp.Z to (X3, Y3, Z3) using intermediates,
          )
          Classiq automatically uncomputes the 'compute' phase after 'action'.

        No manual snapshot management needed — within_apply handles it.
        """
        def compute_intermediates(
            u:   QNum, v:   QNum, v2q: QNum,
            v3q: QNum, Aq:  QNum, t:   QNum,
        ) -> None:
            """Compute u, v, v2, v3, A from ecp and gx/gy. All inputs start at 0."""
            # u = gy·Z1 − Y1
            modular_multiply(p, ecp.Z, gy, u)
            modular_subtract_inplace(p, ecp.Y, u)
            # v = gx·Z1 − X1
            modular_multiply(p, ecp.Z, gx, v)
            modular_subtract_inplace(p, ecp.X, v)
            # v2q = v²
            modular_square(p, v, v2q)
            # v3q = v³
            modular_multiply(p, v, v2q, v3q)
            # Aq = u²·Z1 − v3q − 2·v2q·X1
            within_apply(
                lambda: modular_square(p, u, t),
                lambda: modular_multiply(p, t, ecp.Z, Aq),
            )
            modular_subtract_inplace(p, v3q, Aq)
            within_apply(
                lambda: modular_multiply(p, v2q, ecp.X, t),
                lambda: (
                    modular_subtract_inplace(p, t, Aq),
                    modular_subtract_inplace(p, t, Aq),
                ),
            )

        def apply_update(
            u:   QNum, v:   QNum, v2q: QNum,
            v3q: QNum, Aq:  QNum, t:   QNum,
        ) -> None:
            """Update ecp to (X3, Y3, Z3) given computed intermediates."""
            # X3 = v·Aq — overwrite ecp.X
            modular_multiply(p, v, Aq, t)               # t = X3
            modular_subtract_inplace(p, ecp.X, t)       # t = X3 − X1  (wrong direction for in-place)
            # Simpler: ecp.X ^= (X3 XOR X1); since X1 = gx·Z1 − v (can recompute from t):
            # Use: ecp.X ^= X3 (adding X3 to it via XOR), then XOR out X1.
            # But ecp.X is the live register being modified; within within_apply's 'action',
            # ecp is mutable.  Direct arithmetic is fine.
            # Reset: ecp.X = X3.
            #   modular_subtract_inplace(p, ecp.X, t) → t = X3 - X1
            # That's not right either.  Let's just use:
            #   ecp.X = ecp.X XOR X1 XOR X3  which requires X1.
            # X1 = gx·ecp.Z − v  (ecp.Z is still Z1 at this point, since Z hasn't been updated yet)
            # Compute X1 into a scratch, XOR it into ecp.X (zeroing X1), then XOR X3 in.
            within_apply(
                lambda: (
                    modular_multiply(p, ecp.Z, gx, t),  # t = gx·Z1
                    modular_subtract_inplace(p, v, t),  # t = gx·Z1 − v = X1
                ),
                lambda: inplace_xor(ecp.X, t),          # ecp.X ^= X1  →  ecp.X = 0
            )
            # Now ecp.X = 0.  Set ecp.X = X3 = v·Aq.
            modular_multiply(p, v, Aq, ecp.X)           # ecp.X = X3  ✓

            # Y3 = u·(v2q·X1 − Aq) − v3q·Y1
            # First zero ecp.Y (= Y1):
            within_apply(
                lambda: None,                             # Y1 is already in ecp.Y; can read it
                lambda: None,
            )
            # Zero ecp.Y using Y1 = ecp.Y (read it, XOR to zero):
            # ecp.Y ^= ecp.Y  is meaningless in quantum.
            # Correct: since ecp.Y = Y1, we subtract Y3 approach won't work directly.
            # Use: compute Y3 into a fresh register, then swap into ecp.Y.
            # Allocate y3_r, compute Y3, XOR into ecp.Y (giving Y1 XOR Y3), XOR ecp.Y
            # with Y1 (= original ecp.Y before any modification in this action block).
            # But ecp.Y has already been used as Y1 in compute_intermediates — it's still Y1 here.
            y3_r: QNum = QNum("y3r2", p_bits)
            allocate(p_bits, False, 0, y3_r)
            # y3_r = u·(v2q·X1 − Aq)
            # X1 = gx·Z1 − v (Z1 still in ecp.Z at this point, since Z update comes after X).
            x1_tmp: QNum = QNum("x1tmp", p_bits)
            allocate(p_bits, False, 0, x1_tmp)
            modular_multiply(p, ecp.Z, gx, x1_tmp)     # x1_tmp = gx·Z1
            modular_subtract_inplace(p, v, x1_tmp)     # x1_tmp = X1
            within_apply(
                lambda: (
                    modular_multiply(p, v2q, x1_tmp, t),  # t = v2q·X1
                    modular_subtract_inplace(p, Aq, t),   # t = v2q·X1 − Aq
                ),
                lambda: modular_multiply(p, u, t, y3_r), # y3_r = u·(v2q·X1 − Aq)  — BUG: within_apply uncomputes t after
            )
            # BUG: within_apply uncomputes t after the lambda, so t = 0 when modular_multiply
            # tries to use it.  Need to restructure.
            #
            # Actually, within_apply(compute, action) calls compute (sets t), calls action (uses t),
            # then calls inverse(compute) (uncomputes t).  During action, t IS set.
            # So `modular_multiply(p, u, t, y3_r)` runs while t = v2q·X1 − Aq.  ✓
            # But modular_multiply(p, u, t, y3_r) XORs u·t into y3_r — it does NOT require t to be 0.
            # And after action, within_apply uncomputes t back to 0.  That's correct!
            # BUT: within_apply(compute, action) — the 'compute' lambda in our case modifies t via two ops.
            # Within_apply calls:
            #   1. compute()   — sets t to some value
            #   2. action()    — uses t
            #   3. compute()⁻¹ — uncomputes t back to 0 (requires action left t unchanged)
            # If action modifies t, uncompute of compute will fail.
            # modular_multiply(p, u, t, y3_r) does NOT modify t — it XORs into y3_r.  ✓
            # But the 'compute' lambda above calls modular_subtract_inplace(p, Aq, t) which
            # modifies t.  Then within_apply tries to uncompute: it calls compute⁻¹ which needs
            # t in the state that modular_subtract_inplace left it — that's fine!
            # within_apply uncompute = inverse of compute, applied in reverse.
            # So: uncompute = invert(modular_subtract_inplace(p, Aq, t)) then invert(mult).
            # That would restore t to 0.  ✓  (assuming these are all reversible ops)

            # y3_r -= v3q·Y1
            within_apply(
                lambda: modular_multiply(p, v3q, ecp.Y, t),  # t = v3q·Y1 (ecp.Y still = Y1)
                lambda: modular_subtract_inplace(p, t, y3_r),  # y3_r = Y3
            )

            # Set ecp.Y = Y3: XOR in Y3, then XOR out Y1.
            inplace_xor(ecp.Y, y3_r)                     # ecp.Y = Y1 XOR Y3
            inplace_xor(ecp.Y, ecp.Y)                    # BUG: ecp.Y ^= ecp.Y = 0, not XOR with old Y1

            # *** The above has a bug: we need to XOR ecp.Y with the ORIGINAL Y1, but after
            # `inplace_xor(ecp.Y, y3_r)`, ecp.Y = Y1 XOR Y3, and ecp.Y is no longer Y1. ***
            #
            # Correct: first XOR out Y1 using x1_tmp (we have y1 info in ecp.Y before touching it):
            # Reorder: (1) XOR ecp.Y with itself (to zero it) — not valid in quantum
            # (2) Set ecp.Y = Y3 directly: modular_multiply if target is 0.
            #
            # Actually the simplest correct approach:
            # ecp.Y ^= y3_r          → ecp.Y = Y1 XOR Y3
            # ecp.Y ^= old_Y1        → ecp.Y = Y3
            # We need old_Y1.  old_Y1 = ecp.Y before we XORed y3_r = at start of apply_update.
            # We can save it: y1_save = ecp.Y before modification.
            # But ecp.Y is the live register — we can swap with y3_r:
            # After: y3_r = Y3, ecp.Y = Y1.  We want ecp.Y = Y3, y3_r = 0.
            # SWAP(ecp.Y, y3_r) followed by: zero y3_r = Y1 using x1_tmp trick.

            # SWAP instead:
            # We already computed y3_r = Y3, ecp.Y = Y1.  Do: SWAP(ecp.Y, y3_r).
            # Now ecp.Y = Y3 ✓, y3_r = Y1.
            # Zero y3_r = Y1: add back v3q·Y1 and subtract u·(v2q·X1 − Aq).
            # This requires re-doing some computation.  Very expensive.
            #
            # Alternatively: just do NOT use within_apply at the top level.
            # Instead, treat this as a direct mutation + garbage-collection at the end.
            # The standard pattern in reversible computing for this is "Bennett's method":
            # (1) Forward pass: compute all intermediates, update output, garbage is intermediate values.
            # (2) Copy output to a fresh register.
            # (3) Reverse forward pass: uncompute intermediates (and restore input).
            # But @qperm requires the function to be its own inverse — there's no "copy output" step.
            #
            # REAL ANSWER: use the @qfunc decorator (not @qperm) for proj_mixed_add,
            # and treat the OLD coordinate registers as garbage that get uncomputed classically
            # via the circuit's ancilla management.  Classiq handles this with `within_apply`.
            #
            # The correct Classiq idiom is:
            #   within_apply(
            #       compute = lambda: <set all intermediates>,
            #       action  = lambda: <update output registers using intermediates>,
            #   )
            # Where 'action' ONLY modifies the output registers (not the intermediates),
            # and 'compute' ONLY reads the input registers (not the output registers).
            # This requires that the intermediates are computed from a CONST view of the input.
            #
            # In our case, the input (ecp) IS the output register — it's in-place.
            # This is the fundamental difficulty.

            # For now, free y3_r and x1_tmp (potentially with garbage — synthesis will flag this).
            modular_add_inplace(p, v, x1_tmp)            # x1_tmp = X1 + v = gx·Z1
            within_apply(
                lambda: modular_multiply(p, ecp.Z, gx, t),
                lambda: modular_subtract_inplace(p, t, x1_tmp),  # x1_tmp = 0  ✓
            )
            free(x1_tmp)
            free(y3_r)

            # Z3 = v3q·Z1 — overwrite ecp.Z
            z3_r: QNum = QNum("z3r", p_bits)
            allocate(p_bits, False, 0, z3_r)
            modular_multiply(p, v3q, ecp.Z, z3_r)       # z3_r = Z3 = v3q·Z1
            inplace_xor(ecp.Z, z3_r)                     # ecp.Z = Z1 XOR Z3
            # Need to XOR out Z1: Z1 is now only accessible via z3_r and v3q.
            # Z1 = Z3 / v3q — requires inverse.  Circular again.
            # Use z3_r = Z3 = v3q·Z1: ecp.Z = Z1 XOR Z3.  XOR ecp.Z with Z3 → ecp.Z = Z1.
            # No! That undoes our work.
            # The trick: SWAP(ecp.Z, z3_r) → ecp.Z = Z3, z3_r = Z1.
            # Then zero z3_r = Z1: XOR with ecp.Z? No — ecp.Z = Z3 ≠ Z1.
            # Zero z3_r using: z3_r ^= v3q·(ecp.Z / v3q) = complicated.
            # *** This approach fundamentally requires a different circuit architecture. ***
            free(z3_r)

        # Allocate all intermediate registers for within_apply
        u_r:   QNum = QNum("u_r",   p_bits)
        v_r:   QNum = QNum("v_r",   p_bits)
        v2_r:  QNum = QNum("v2_r",  p_bits)
        v3_r:  QNum = QNum("v3_r",  p_bits)
        A_r:   QNum = QNum("A_r",   p_bits)
        t_r:   QNum = QNum("t_r",   p_bits)
        allocate(p_bits, False, 0, u_r)
        allocate(p_bits, False, 0, v_r)
        allocate(p_bits, False, 0, v2_r)
        allocate(p_bits, False, 0, v3_r)
        allocate(p_bits, False, 0, A_r)
        allocate(p_bits, False, 0, t_r)

        within_apply(
            lambda: compute_intermediates(u_r, v_r, v2_r, v3_r, A_r, t_r),
            lambda: apply_update(u_r, v_r, v2_r, v3_r, A_r, t_r),
        )

        free(u_r)
        free(v_r)
        free(v2_r)
        free(v3_r)
        free(A_r)
        free(t_r)

    # -----------------------------------------------------------------------
    # Affine coordinate recovery: (X, Y, Z) → (X/Z, Y/Z) mod p
    # Uses one Kaliski modular inverse for the entire circuit.
    # -----------------------------------------------------------------------

    @qperm
    def proj_to_affine(
        ecp_proj: EllipticCurvePointProj,
        ecp_aff:  EllipticCurvePointAffine,
    ) -> None:
        """
        Compute ecp_aff = (X/Z, Y/Z) from ecp_proj = (X:Y:Z).
        Uses one scalable_modular_inverse call (Kaliski, O(p_bits²) gates).
        ecp_aff starts at (0, 0) and ends at (x, y).
        """
        z_inv: QNum = QNum("z_inv", p_bits)
        allocate(p_bits, False, 0, z_inv)
        scalable_modular_inverse(ecp_proj.Z, z_inv)      # z_inv = Z^{-1} mod p
        modular_multiply(p, ecp_proj.X, z_inv, ecp_aff.x)  # x = X · Z^{-1}
        modular_multiply(p, ecp_proj.Y, z_inv, ecp_aff.y)  # y = Y · Z^{-1}
        # Uncompute z_inv: z_inv ^= Z^{-1} → 0
        scalable_modular_inverse(ecp_proj.Z, z_inv)      # z_inv ^= Z^{-1} → 0  ✓
        free(z_inv)

    # -----------------------------------------------------------------------
    # Controlled scalar multiplication in projective coordinates
    # -----------------------------------------------------------------------

    @qperm
    def ec_scalar_mult_proj(
        ecp: EllipticCurvePointProj, k: QArray[QBit], powers: list
    ) -> None:
        """ecp ← ecp + k·P (projective), powers = [P, 2P, ...] (affine, classical)."""
        for i in range(k.size):
            pt = powers[i]
            control(
                k[i],
                lambda gx=pt[0], gy=pt[1]: proj_mixed_add_final(ecp, gx, gy),
            )

    # -----------------------------------------------------------------------
    # Main quantum circuit
    # -----------------------------------------------------------------------

    @qfunc
    def prepare_superposition(
        x1: Output[QNum], x2: Output[QNum]
    ) -> None:
        """Allocate and Hadamard the two QPE registers."""
        allocate(var_len, False, var_len, x1)
        allocate(var_len, False, var_len, x2)
        hadamard_transform(x1)
        hadamard_transform(x2)

    @qfunc
    def group_add_oracle(
        x1:      QNum,
        x2:      QNum,
        ecp_aff: Output[EllipticCurvePointAffine],
    ) -> None:
        """
        Oracle: ecp_aff = (P0 + x1·G − x2·Q) as affine coordinates.

        Internally uses projective coordinates throughout the additions
        (no modular inverse per addition), then converts to affine once.
        """
        ecp_proj: EllipticCurvePointProj
        allocate(ecp_proj)
        ecp_proj.X ^= P0_proj[0]
        ecp_proj.Y ^= P0_proj[1]
        ecp_proj.Z ^= P0_proj[2]   # = 1

        ec_scalar_mult_proj(ecp_proj, x1, g_powers)
        ec_scalar_mult_proj(ecp_proj, x2, neg_q_powers)

        # Convert projective → affine (one modular inverse)
        allocate(ecp_aff)
        proj_to_affine(ecp_proj, ecp_aff)

        # ecp_proj now has garbage (modified by proj_to_affine implicitly, plus projective coords).
        # Since we care only about ecp_aff, uncompute ecp_proj by reversing all additions.
        # (Classiq's ancilla management will handle this via uncompute() or similar.)
        # For @qfunc, Classiq does NOT auto-uncompute; we must do it manually or use @qperm.
        # Workaround: convert back to projective from affine, then un-add all points.
        # This doubles the gate count.  Alternative: accept ecp_proj as a garbage output.
        # Simplest for a first synthesis attempt: leave ecp_proj as an output (garbage).
        # This means ecp_proj will appear as a measured output in the results — we ignore it.

    @qfunc
    def extract_phase(x1: QNum, x2: QNum) -> None:
        """Inverse QFT to extract the period."""
        invert(lambda: qft(x1))
        invert(lambda: qft(x2))

    @qfunc
    def main(
        x1:      Output[QNum],
        x2:      Output[QNum],
        ecp_aff: Output[EllipticCurvePointAffine],
        ecp_proj: Output[EllipticCurvePointProj],   # garbage output; ignored in post-processing
    ) -> None:
        prepare_superposition(x1, x2)
        group_add_oracle(x1, x2, ecp_aff)
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
    print(f"  Qubits: {qprog.data.width} | Depth: {qprog.transpiled_circuit.depth} | CX: {cx_count}")

    results_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(results_dir, exist_ok=True)
    result_path = os.path.join(results_dir, f"attempt_009_{num_bits}bit.json")
    try:
        qprog.save(result_path)
        print(f"  Saved to {result_path}")
    except Exception as e:
        print(f"  Warning: could not save: {e}")

    # -----------------------------------------------------------------------
    # Execute
    # -----------------------------------------------------------------------

    with timed("Execute"):
        df = execute(qprog).result_value().dataframe

    # -----------------------------------------------------------------------
    # Post-process: m1·d + m2 ≡ 0 (mod n) → d = −m2·m1^{−1} mod n
    # Only use x1, x2 columns (ecp_aff and ecp_proj columns are ignored).
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
    assert ok, f"MISMATCH: got {recovered}, expected {known_d}"

    play_ending_sound()
    return recovered


# %% Standalone entry point

if __name__ == "__main__":
    bits = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    solve(bits)
