"""
test_ibm_hardware.py — Bell state test on IBM hardware via Classiq.

Tries three backends in order:
  1. Real IBM hardware (ibm_torino) via Classiq's credentials (run_via_classiq=True)
  2. IBM noise model emulation (ibm_torino noise, Classiq AerSimulator)
  3. Classiq simulator (baseline)

Run with: python test_ibm_hardware.py [real|emulate|sim]
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
    mode = sys.argv[1] if len(sys.argv) > 1 else "real"

    if mode == "real":
        backend_prefs = IBMBackendPreferences(
            backend_name="ibm_torino",
            run_via_classiq=True,
        )
        run_bell("IBM ibm_torino (via Classiq credentials)", backend_prefs)

    elif mode == "emulate":
        backend_prefs = IBMBackendPreferences(
            backend_name="ibm_torino",
            emulate=True,
        )
        run_bell("IBM ibm_torino noise model (AerSimulator emulation)", backend_prefs)

    elif mode == "sim":
        backend_prefs = ClassiqBackendPreferences(backend_name="simulator")
        run_bell("Classiq Simulator (no noise)", backend_prefs)

    else:
        print(f"Unknown mode: {mode!r}. Use: real | emulate | sim")
        sys.exit(1)
