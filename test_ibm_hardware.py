"""
test_ibm_hardware.py — Bell state test on real IBM quantum hardware via Classiq.

Credentials are read from environment variables (set in .env, never committed):
  IBM_TOKEN        — IBM Cloud API token
  IBM_INSTANCE     — IBM Cloud instance CRN
  IBM_CHANNEL      — channel, e.g. "ibm_cloud"  (default: ibm_cloud)
  IBM_BACKEND      — backend name               (default: ibm_torino)

Source .env before running:
  set -a; source .env; set +a   # bash/zsh

Run with: python test_ibm_hardware.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from classiq import *
from utils import timed

# -------------------------------------------------------------------------
# Simple Bell state circuit: |00⟩ → (|00⟩ + |11⟩) / √2
# -------------------------------------------------------------------------

@qfunc
def main(q0: Output[QBit], q1: Output[QBit]) -> None:
    allocate(1, q0)
    allocate(1, q1)
    H(q0)
    CX(q0, q1)


def run_bell(backend_label: str, backend_prefs) -> None:
    print(f"\n{'='*60}")
    print(f"Backend: {backend_label}")
    print(f"{'='*60}")

    qmod = create_model(
        main,
        execution_preferences=ExecutionPreferences(
            backend_preferences=backend_prefs,
            num_shots=1000,
        ),
    )

    with timed("Synthesize"):
        qprog = synthesize(qmod)

    ops = qprog.transpiled_circuit.count_ops
    print(f"  Qubits: {qprog.data.width} | CX: {ops.get('cx', 'N/A')}")

    with timed("Execute"):
        result = execute(qprog).result_value()

    df = result.dataframe.sort_values("counts", ascending=False)
    print(df.to_string(index=False))

    # Basic sanity: only |00⟩ and |11⟩ should appear
    states = set(df.apply(lambda r: f"q0={int(r['q0'])} q1={int(r['q1'])}", axis=1))
    expected = {"q0=0 q1=0", "q0=1 q1=1"}
    ok = states.issubset(expected)
    print(f"\n  Bell state check: {'✅ PASS' if ok else '❌ FAIL'} (states seen: {states})")


if __name__ == "__main__":
    IBM_TOKEN    = os.environ.get("IBM_TOKEN")
    IBM_INSTANCE = os.environ.get("IBM_INSTANCE")
    IBM_CHANNEL  = os.environ.get("IBM_CHANNEL", "ibm_cloud")
    IBM_BACKEND  = os.environ.get("IBM_BACKEND", "ibm_torino")

    if not IBM_TOKEN or not IBM_INSTANCE:
        print("ERROR: IBM_TOKEN and IBM_INSTANCE must be set (source .env first)")
        sys.exit(1)

    backend_prefs = IBMBackendPreferences(
        backend_name=IBM_BACKEND,
        access_token=IBM_TOKEN,
        channel=IBM_CHANNEL,
        instance_crn=IBM_INSTANCE,
    )
    run_bell(f"IBM {IBM_BACKEND} (your credentials)", backend_prefs)
