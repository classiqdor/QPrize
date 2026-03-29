# =============================================================================
# Attempt 002 — 2026-03-29
#
# Goal: Baseline using the colleague's group-index encoding approach.
#       Verify 4-bit and 6-bit on the Classiq simulator.
#
# Previous attempt (001): Used naive (x,y) coordinate representation — obsolete.
#   The colleague already implemented group-index encoding which is far superior:
#   points stored as scalar k (meaning k·G) instead of (x,y), so the oracle
#   reduces to controlled modular additions of precomputed constants.
#   No quantum modular inversion needed.
#
# Circuit formula:
#   ecp_idx = INITIAL_IDX + Σᵢ x1[i]·2ⁱ + Σᵢ x2[i]·(n-d)·2ⁱ  (mod n)
#   Constants are all classical — precomputed from known n, d.
#
# Variants:
#   - Ripple-carry: modular_add_constant_inplace  (proven on hardware for 4-bit)
#   - QFT-space:   modular_add_qft_space          (57% fewer CX for 6-bit+)
#
# This attempt: establish clean baseline in our framework before optimizing.
# =============================================================================

# %% Imports & parameters
import sys
sys.path.insert(0, "..")

import numpy as np
from classiq import *

from consts import PARAMS
from utils import timed, play_ending_sound

TARGET_BITS = 4   # change to 6 for 6-bit

params          = PARAMS[TARGET_BITS]
GENERATOR_ORDER = params.n
KNOWN_D         = params.d

VAR_LEN     = GENERATOR_ORDER.bit_length()
IDX_BITS    = GENERATOR_ORDER.bit_length()
INITIAL_IDX = 2

NEG_Q_STEP  = (GENERATOR_ORDER - KNOWN_D) % GENERATOR_ORDER
G_STEPS     = [(1 << i) % GENERATOR_ORDER for i in range(VAR_LEN)]
NEGQ_STEPS  = [(NEG_Q_STEP * (1 << i)) % GENERATOR_ORDER for i in range(VAR_LEN)]

USE_QFT_ADDER = (TARGET_BITS >= 6)

print(f"Attempt 002 — {TARGET_BITS}-bit | n={GENERATOR_ORDER} | d={KNOWN_D}")
print(f"VAR_LEN={VAR_LEN} | IDX_BITS={IDX_BITS} | variant={'QFT-space' if USE_QFT_ADDER else 'ripple-carry'}")
print(f"G_STEPS={G_STEPS}")
print(f"NEGQ_STEPS={NEGQ_STEPS}")


# %% Quantum circuits

@qfunc
def shor_ecdlp_ripple(
    x1: Output[QArray[QBit]],
    x2: Output[QArray[QBit]],
    ecp_idx: Output[QNum[IDX_BITS, False, 0]],
) -> None:
    allocate(VAR_LEN, x1)
    allocate(VAR_LEN, x2)
    allocate(IDX_BITS, False, 0, ecp_idx)
    ecp_idx ^= INITIAL_IDX
    hadamard_transform(x1)
    hadamard_transform(x2)
    for i in range(VAR_LEN):
        control(x1[i], lambda k=G_STEPS[i]:
                modular_add_constant_inplace(GENERATOR_ORDER, k, ecp_idx))
    for i in range(VAR_LEN):
        control(x2[i], lambda k=NEGQ_STEPS[i]:
                modular_add_constant_inplace(GENERATOR_ORDER, k, ecp_idx))
    invert(lambda: qft(x1))
    invert(lambda: qft(x2))


@qfunc
def shor_ecdlp_qft(
    x1: Output[QArray[QBit]],
    x2: Output[QArray[QBit]],
    ecp_phi: Output[QArray[QBit]],
) -> None:
    allocate(VAR_LEN, x1)
    allocate(VAR_LEN, x2)
    ecp = QNum[IDX_BITS, False, 0]()
    allocate(IDX_BITS, False, 0, ecp)
    ecp ^= INITIAL_IDX
    qft(ecp)
    bind(ecp, ecp_phi)
    hadamard_transform(x1)
    hadamard_transform(x2)
    for i in range(VAR_LEN):
        control(x1[i], lambda k=G_STEPS[i]:
                modular_add_qft_space(GENERATOR_ORDER, k, ecp_phi))
    for i in range(VAR_LEN):
        control(x2[i], lambda k=NEGQ_STEPS[i]:
                modular_add_qft_space(GENERATOR_ORDER, k, ecp_phi))
    invert(lambda: qft(ecp_phi))
    invert(lambda: qft(x1))
    invert(lambda: qft(x2))


if USE_QFT_ADDER:
    @qfunc
    def main(
        x1: Output[QArray[QBit]],
        x2: Output[QArray[QBit]],
        ecp_phi: Output[QArray[QBit]],
    ) -> None:
        shor_ecdlp_qft(x1, x2, ecp_phi)
else:
    @qfunc
    def main(
        x1: Output[QArray[QBit]],
        x2: Output[QArray[QBit]],
        ecp_idx: Output[QNum[IDX_BITS, False, 0]],
    ) -> None:
        shor_ecdlp_ripple(x1, x2, ecp_idx)


# %% Post-processing

def extract_d(df):
    import math
    N = 1 << VAR_LEN
    df = df.copy()

    def to_int(v):
        if isinstance(v, (int, float)): return int(v)
        return sum(int(b) * (1 << i) for i, b in enumerate(v))

    df["x1_r"] = (df["x1"].apply(to_int) / N * GENERATOR_ORDER).round().astype(int) % GENERATOR_ORDER
    df["x2_r"] = (df["x2"].apply(to_int) / N * GENERATOR_ORDER).round().astype(int) % GENERATOR_ORDER
    df = df[df["x1_r"].apply(lambda v: math.gcd(int(v), GENERATOR_ORDER) == 1)].copy()
    df["d_candidate"] = (-df["x2_r"] * df["x1_r"].apply(lambda v: pow(int(v), -1, GENERATOR_ORDER))) % GENERATOR_ORDER
    return df


# %% Synthesize & execute

constraints = Constraints(max_width=200)
preferences = Preferences(optimization_level=0, timeout_seconds=3600)
qmod = create_model(main, constraints=constraints, preferences=preferences)

with timed("Synthesize"):
    qprog = synthesize(qmod)

ops = qprog.transpiled_circuit.count_ops
print(f"Qubits: {qprog.data.width}")
print(f"Depth:  {qprog.transpiled_circuit.depth}")
print(f"CX:     {ops.get('cx', 'N/A')}")
print(f"Ops:    {ops}")

with timed("Execute"):
    res = execute(qprog).result_value()

df = res.dataframe.sort_values("counts", ascending=False)
df["probability"] = df["counts"] / df["counts"].sum()
print(f"\nTop 10 outcomes ({len(df)} distinct, {df['counts'].sum()} shots):")
print(df.head(10).to_string(index=False))

df_log = extract_d(df)
if df_log.empty:
    print("No valid measurements.")
else:
    recovered = int(df_log["d_candidate"].mode()[0])
    print(f"\nRecovered d = {recovered}")
    print(f"Expected  d = {KNOWN_D}")
    match = recovered == KNOWN_D
    print(f"{'✅ CORRECT' if match else '❌ MISMATCH'}")
    assert match, f"Got {recovered}, expected {KNOWN_D}"

play_ending_sound()
