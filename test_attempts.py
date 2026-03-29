# =============================================================================
# Test suite: verify that the latest registered attempt recovers d for each
# supported bit size.
#
# Run:   pytest test_attempts.py -v
#        pytest test_attempts.py -v -k "bits4"   # single bit size
#
# Expected durations (per registry.py):
#   4-bit  ~15s
#   6-bit  ~60s
# =============================================================================

import importlib
import time
import pytest

from consts import PARAMS
from attempts.registry import LATEST


def load_attempt(module_name):
    return importlib.import_module(f"attempts.{module_name}")


@pytest.mark.parametrize(
    "bits",
    sorted(LATEST.keys()),
    ids=[f"bits{b}" for b in sorted(LATEST.keys())],
)
def test_solve(bits):
    entry   = LATEST[bits][-1]  # latest working attempt for this bit size
    module  = load_attempt(entry["attempt"])
    expected_d = PARAMS[bits].d
    eta     = entry["expected_seconds"]

    print(f"\n[{entry['attempt']}] bits={bits} | expected ~{eta}s | d={expected_d}")

    t0 = time.time()
    recovered = module.solve(bits)
    elapsed = time.time() - t0

    print(f"  done in {elapsed:.1f}s")
    assert recovered == expected_d, f"Got d={recovered}, expected d={expected_d}"
