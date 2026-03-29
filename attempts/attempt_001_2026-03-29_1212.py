# =============================================================================
# Attempt 001 — 2026-03-29
#
# Goal: Baseline port of the classiq-library elliptic curve DL notebook to the
#       QDay competition curves (a=0, b=7). Verify on the 4-bit case (p=13,
#       n=7, G=(11,5), Q=(11,8), expected d=6) on the Classiq simulator.
#
# Previous attempt: none (first attempt)
#
# Strategy: minimal changes from the notebook — keep mock_modular_inverse (lookup
#   table), keep (x,y) coordinate representation. Just swap in competition params.
# =============================================================================

# %% Imports & parameters
import sys
sys.path.insert(0, "..")

import numpy as np
from classiq import *
from classiq.qmod.symbolic import ceiling, log, subscript
import math

from consts import PARAMS, EllipticCurve
from utils import timed, play_ending_sound

params = PARAMS[4]
CURVE = EllipticCurve(params)
GENERATOR_G      = list(params.G)
GENERATOR_ORDER  = params.n
INITIAL_POINT    = list(params.G)   # use G as starting point
TARGET_POINT     = list(params.Q)   # public key Q = d*G

print(f"Curve: y^2 = x^3 + {CURVE.a}x + {CURVE.b} (mod {CURVE.p})")
print(f"G={GENERATOR_G}, order={GENERATOR_ORDER}, Q={TARGET_POINT}, expected d={params.d}")


# %% Quantum data structures

class EllipticCurvePoint(QStruct):
    x: QNum[CURVE.p.bit_length()]
    y: QNum[CURVE.p.bit_length()]


# %% Classical helpers

def ell_double_classical(P, curve):
    p = curve.p
    x, y = P
    s = ((3 * x * x + curve.a) * pow(2 * y, -1, p)) % p
    xr = (s * s - 2 * x) % p
    yr = (y - s * ((x - xr) % p)) % p
    return [xr, (p - yr) % p]


# %% Quantum functions

@qperm
def mock_modular_inverse(x: Const[QNum], result: QNum, modulus: int) -> None:
    inverse_table = lookup_table(
        lambda _x: pow(_x, -1, modulus) if math.gcd(_x, modulus) == 1 else 0, x
    )
    result ^= subscript(inverse_table, x)


@qperm
def ec_point_add(ecp: EllipticCurvePoint, G: list[int], p: int) -> None:
    n = CURVE.p.bit_length()
    slope = QNum()
    allocate(n, slope)
    t0 = QNum()
    allocate(n, t0)

    Gx, Gy = G[0], G[1]

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
            lambda: (
                allocate(CURVE.p.bit_length(), t1),
                modular_multiply(p, t0, ecp.y, t1),
            ),
            lambda: inplace_xor(t1, slope),
        ),
    )
    free(slope)

    modular_add_constant_inplace(p, (-Gy) % p, ecp.y)
    modular_negate_inplace(p, ecp.x)
    modular_add_constant_inplace(p, Gx, ecp.x)


@qperm
def ec_scalar_mult_add(
    ecp: EllipticCurvePoint,
    k: QArray[QBit],
    P: list[int],
    p: int,
    a: int,
    b: int,
) -> None:
    current_power = P.copy()
    for i in range(k.size):
        control(k[i], lambda: ec_point_add(ecp, current_power, p))
        if i < k.size - 1:
            current_power = ell_double_classical(current_power, EllipticCurve(p, a, b))  # classic helper, p/a/b form ok here


@qfunc
def shor_ecdlp(
    x1: Output[QNum],
    x2: Output[QNum],
    ecp: Output[EllipticCurvePoint],
    P_0: list[int],
    G: list[int],
    P_target: list[int],
) -> None:
    var_len = GENERATOR_ORDER.bit_length()
    allocate(var_len, False, var_len, x1)
    allocate(var_len, False, var_len, x2)

    allocate(ecp)
    ecp.x ^= P_0[0]
    ecp.y ^= P_0[1]

    hadamard_transform(x1)
    hadamard_transform(x2)

    ec_scalar_mult_add(ecp, x1, G, CURVE.p, CURVE.a, CURVE.b)

    neg_target = [P_target[0], (-P_target[1]) % CURVE.p]
    ec_scalar_mult_add(ecp, x2, neg_target, CURVE.p, CURVE.a, CURVE.b)

    invert(lambda: qft(x1))
    invert(lambda: qft(x2))


# %% Synthesize & run

@qfunc
def main(x1: Output[QNum], x2: Output[QNum], ecp: Output[EllipticCurvePoint]) -> None:
    shor_ecdlp(x1, x2, ecp, INITIAL_POINT, GENERATOR_G, TARGET_POINT)


constraints = Constraints(optimization_parameter="width")
preferences = Preferences(timeout_seconds=3600, optimization_level=1, qasm3=True)
qmod = create_model(main, constraints=constraints, preferences=preferences)

with timed("Synthesize"):
    qprog = synthesize(qmod)
print(f"Qubits: {qprog.data.width}")
print(f"Depth:  {qprog.transpiled_circuit.depth}")
print(f"Ops:    {qprog.transpiled_circuit.count_ops}")


# %% Execute & post-process

with timed("Execute"):
    res = execute(qprog).result_value()
df = res.dataframe
df["probability"] = df["counts"] / df["counts"].sum()
df_sorted = df.sort_values("counts", ascending=False)

print(f"\nDistinct outcomes: {len(df)}, Total shots: {df['counts'].sum()}")
print(df_sorted.head(10))


def closest_fraction(x, denom):
    return round(x * denom)

df_sorted["x1_rounded"] = closest_fraction(df_sorted.x1, GENERATOR_ORDER)
df_sorted["x2_rounded"] = closest_fraction(df_sorted.x2, GENERATOR_ORDER)

df_sorted = df_sorted[np.gcd(df_sorted.x2_rounded.astype(int), GENERATOR_ORDER) == 1].copy()
df_sorted["x2_inverse"] = [pow(int(a), -1, GENERATOR_ORDER) for a in df_sorted.x2_rounded]
df_sorted["d_candidate"] = (-df_sorted.x1_rounded * df_sorted.x2_inverse) % GENERATOR_ORDER

print("\nTop candidates for d:")
print(df_sorted[["x1_rounded", "x2_rounded", "d_candidate", "counts"]].head(10))

recovered = df_sorted["d_candidate"].mode()[0]
print(f"\nRecovered d = {int(recovered)}, expected d = {params.d}")
assert int(recovered) == params.d, f"MISMATCH: got {recovered}, expected {params.d}"
print("SUCCESS")
play_ending_sound()
