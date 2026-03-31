"""
run_scalar_on_hardware.py — Run attempt_example_scalar on IBM quantum hardware.

DEFAULT: Classiq simulator (safe, free, instant).
HARDWARE: Pass --ibm explicitly to run on real IBM hardware.

Usage:
    python run_scalar_on_hardware.py           # simulator
    python run_scalar_on_hardware.py --ibm     # real IBM hardware (costs budget!)

IBM credentials are read from .env (set IBM_TOKEN, IBM_INSTANCE, IBM_CHANNEL, IBM_BACKEND).
Source before running: set -a; source .env; set +a
"""

import math
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from classiq import *

from consts import PARAMS
from attempts.attempt_example_scalar import precompute_oracle_constants
from utils import timed, play_ending_sound

NUM_BITS = 4   # 4-bit curve: 11 qubits, 716 CX — smallest viable circuit


def build_backend(use_ibm: bool):
    if not use_ibm:
        return ClassiqBackendPreferences(backend_name="simulator")

    token    = os.environ.get("IBM_TOKEN")
    instance = os.environ.get("IBM_INSTANCE")
    channel  = os.environ.get("IBM_CHANNEL", "ibm_cloud")
    backend  = os.environ.get("IBM_BACKEND", "ibm_torino")

    if not token or not instance:
        print("ERROR: IBM_TOKEN and IBM_INSTANCE must be set (source .env first)")
        sys.exit(1)

    return IBMBackendPreferences(
        backend_name=backend,
        access_token=token,
        channel=channel,
        instance_crn=instance,
    )


def run(use_ibm: bool) -> int:
    params  = PARAMS[NUM_BITS]
    n       = params.n
    known_d = params.d

    var_len     = n.bit_length()
    idx_bits    = n.bit_length()
    N           = 1 << var_len
    initial_idx = 2

    g_steps, negq_steps = precompute_oracle_constants(params, var_len)

    backend_label = f"IBM {os.environ.get('IBM_BACKEND', 'ibm_torino')}" if use_ibm else "Classiq Simulator"
    print(f"\n[scalar {NUM_BITS}-bit] n={n} | backend={backend_label}")

    # -------------------------------------------------------------------------
    # Circuit (identical to attempt_example_scalar)
    # -------------------------------------------------------------------------

    @qfunc
    def prepare_superposition(x1: Output[QArray[QBit]], x2: Output[QArray[QBit]]) -> None:
        allocate(var_len, x1)
        allocate(var_len, x2)
        hadamard_transform(x1)
        hadamard_transform(x2)

    @qfunc
    def group_add_oracle(x1: QArray[QBit], x2: QArray[QBit], ecp_idx: Output[QNum[idx_bits, False, 0]]) -> None:
        allocate(idx_bits, False, 0, ecp_idx)
        ecp_idx ^= initial_idx
        for i in range(var_len):
            control(x1[i], lambda k=g_steps[i]: modular_add_constant_inplace(n, k, ecp_idx))
        for i in range(var_len):
            control(x2[i], lambda k=negq_steps[i]: modular_add_constant_inplace(n, k, ecp_idx))

    @qfunc
    def extract_phase(x1: QArray[QBit], x2: QArray[QBit]) -> None:
        invert(lambda: qft(x1))
        invert(lambda: qft(x2))

    @qfunc
    def main(x1: Output[QArray[QBit]], x2: Output[QArray[QBit]], ecp_idx: Output[QNum[idx_bits, False, 0]]) -> None:
        prepare_superposition(x1, x2)
        group_add_oracle(x1, x2, ecp_idx)
        extract_phase(x1, x2)

    # -------------------------------------------------------------------------
    # Synthesize + execute
    # -------------------------------------------------------------------------

    qmod = create_model(
        main,
        constraints=Constraints(max_width=200),
        preferences=Preferences(optimization_level=1, timeout_seconds=3600),
        execution_preferences=ExecutionPreferences(
            backend_preferences=build_backend(use_ibm),
            num_shots=1000,
        ),
    )

    with timed("Synthesize"):
        qprog = synthesize(qmod)

    ops = qprog.transpiled_circuit.count_ops
    print(f"  Qubits: {qprog.data.width} | Depth: {qprog.transpiled_circuit.depth} | CX: {ops.get('cx', 'N/A')}")

    with timed("Execute"):
        res = execute(qprog).result_value()

    df = res.dataframe.sort_values("counts", ascending=False)

    def to_int(v):
        if isinstance(v, (int, float)):
            return int(v)
        return sum(int(b) * (1 << i) for i, b in enumerate(v))

    df["x1_r"] = (df["x1"].apply(to_int) / N * n).round().astype(int) % n
    df["x2_r"] = (df["x2"].apply(to_int) / N * n).round().astype(int) % n
    df = df[df["x1_r"].apply(lambda v: math.gcd(int(v), n) == 1)].copy()
    df["d_candidate"] = (-df["x2_r"] * df["x1_r"].apply(lambda v: pow(int(v), -1, n))) % n

    recovered = int(df["d_candidate"].mode()[0])
    match = recovered == known_d
    print(f"  Recovered d={recovered}, expected d={known_d} → {'✅' if match else '❌'}")

    play_ending_sound()
    return recovered


if __name__ == "__main__":
    use_ibm = "--ibm" in sys.argv
    if use_ibm:
        print("⚠️  Running on REAL IBM hardware — this consumes budget!")
    run(use_ibm)
