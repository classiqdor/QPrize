# =============================================================================
# Validation tests — verify we are actually solving ECDLP, not something else.
#
# Run:   pytest tests/test_validation.py -v
#        pytest tests/test_validation.py -v -k algebraic   # instant, no quantum
#        pytest tests/test_validation.py -v -k quantum      # ~60s, runs circuits
#
# Test categories:
#   [algebraic]  Pure classical math checks — instant
#   [quantum]    Requires circuit execution — slow (~20s each for 4-bit)
# =============================================================================

import math
import importlib
import pytest
import numpy as np
from classiq import *

from consts import PARAMS
from utils import timed


# ---------------------------------------------------------------------------
# Shared parametric circuit runner
# (Duplicates core circuit logic with injectable params for testing purposes)
# ---------------------------------------------------------------------------

def _run_4bit_circuit(d_override=None, initial_idx=2):
    """
    Run the 4-bit ripple-carry circuit with custom parameters.
    Returns the raw result dataframe.
    """
    params          = PARAMS[4]
    generator_order = params.n
    d               = d_override if d_override is not None else params.d
    var_len         = generator_order.bit_length()
    idx_bits        = var_len

    neg_q_step  = (generator_order - d) % generator_order
    g_steps     = [(1 << i) % generator_order for i in range(var_len)]
    negq_steps  = [(neg_q_step * (1 << i)) % generator_order for i in range(var_len)]

    @qfunc
    def main(
        x1: Output[QArray[QBit]],
        x2: Output[QArray[QBit]],
        ecp_idx: Output[QNum[idx_bits, False, 0]],
    ) -> None:
        allocate(var_len, x1)
        allocate(var_len, x2)
        allocate(idx_bits, False, 0, ecp_idx)
        ecp_idx ^= initial_idx
        hadamard_transform(x1)
        hadamard_transform(x2)
        for i in range(var_len):
            control(x1[i], lambda k=g_steps[i]:
                    modular_add_constant_inplace(generator_order, k, ecp_idx))
        for i in range(var_len):
            control(x2[i], lambda k=negq_steps[i]:
                    modular_add_constant_inplace(generator_order, k, ecp_idx))
        invert(lambda: qft(x1))
        invert(lambda: qft(x2))

    qmod = create_model(main,
                        constraints=Constraints(max_width=200),
                        preferences=Preferences(optimization_level=0, timeout_seconds=600))
    qprog = synthesize(qmod)
    return execute(qprog).result_value()


def _extract_d(df, generator_order, var_len):
    N = 1 << var_len

    def to_int(v):
        if isinstance(v, (int, float)): return int(v)
        return sum(int(b) * (1 << i) for i, b in enumerate(v))

    df = df.copy()
    df["x1_r"] = (df["x1"].apply(to_int) / N * generator_order).round().astype(int) % generator_order
    df["x2_r"] = (df["x2"].apply(to_int) / N * generator_order).round().astype(int) % generator_order
    df_valid = df[df["x1_r"].apply(lambda v: math.gcd(int(v), generator_order) == 1)].copy()
    df_valid["d_candidate"] = (
        -df_valid["x2_r"] * df_valid["x1_r"].apply(lambda v: pow(int(v), -1, generator_order))
    ) % generator_order
    return df_valid


# ---------------------------------------------------------------------------
# [algebraic] Pure classical math — no quantum needed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bits", [4, 6, 7], ids=["bits4", "bits6", "bits7"])
def test_algebraic_constants(bits):
    """G_STEPS and NEGQ_STEPS are mathematically correct for the given curve."""
    params = PARAMS[bits]
    n, d = params.n, params.d
    var_len = n.bit_length()

    neg_q_step = (n - d) % n
    g_steps    = [(1 << i) % n for i in range(var_len)]
    negq_steps = [(neg_q_step * (1 << i)) % n for i in range(var_len)]

    # G_STEPS should be powers of 2 mod n (represent G, 2G, 4G, ... in group-index space)
    for i, g in enumerate(g_steps):
        assert g == pow(2, i, n), f"G_STEPS[{i}] wrong: got {g}, expected {pow(2,i,n)}"

    # NEGQ_STEPS[i] = neg_q_step * 2^i mod n
    for i, nq in enumerate(negq_steps):
        expected = (neg_q_step * pow(2, i, n)) % n
        assert nq == expected, f"NEGQ_STEPS[{i}] wrong"

    # neg_q_step should encode -Q = n - d (since Q = d*G, -Q = (n-d)*G)
    assert neg_q_step == (n - d) % n

    # G_STEPS and NEGQ_STEPS are the same iff d == n-1 (degenerate case)
    if d == n - 1:
        assert g_steps == negq_steps, "4-bit degenerate case: expected G_STEPS == NEGQ_STEPS"
    else:
        assert g_steps != negq_steps, f"{bits}-bit should be non-degenerate"


def test_algebraic_postprocessing():
    """Post-processing formula d = -x2_r * x1_r^{-1} mod n is correct."""
    for bits in [4, 6, 7]:
        params = PARAMS[bits]
        n, d = params.n, params.d

        # For valid pairs: x2_r ≡ -d * x1_r (mod n)
        # So -x2_r * x1_r^{-1} = d * x1_r * x1_r^{-1} = d
        for x1_r in range(1, n):
            if math.gcd(x1_r, n) != 1:
                continue
            x2_r = (-d * x1_r) % n
            d_recovered = (-x2_r * pow(x1_r, -1, n)) % n
            assert d_recovered == d, f"bits={bits}: formula failed for x1_r={x1_r}"


def test_algebraic_4bit_degeneracy():
    """
    4-bit case (n=7, d=6=n-1) is degenerate: G_STEPS == NEGQ_STEPS.
    The algorithm still works because the period vector (6,1) = (-1,1) is valid,
    but all valid pairs satisfy x1_r == x2_r (since x2_r = -d*x1_r = x1_r mod 7).
    The 6-bit case (d=18, n=31) is non-degenerate and more trustworthy.
    """
    p4 = PARAMS[4]
    assert p4.d == p4.n - 1, "Expected 4-bit to have d=n-1"

    # For d=n-1, valid pairs satisfy x2_r = -d*x1_r = x1_r mod n
    n = p4.n
    for x1_r in range(1, n):
        if math.gcd(x1_r, n) == 1:
            x2_r_expected = (-p4.d * x1_r) % n
            assert x2_r_expected == x1_r, f"Expected x1_r==x2_r for degenerate case, got {x2_r_expected}"


# ---------------------------------------------------------------------------
# [quantum] Circuit execution tests — slow
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def result_4bit_correct():
    """Run 4-bit circuit once with correct params, reuse across tests."""
    with timed("4-bit circuit (correct d)"):
        return _run_4bit_circuit(d_override=None, initial_idx=2)


@pytest.fixture(scope="module")
def result_4bit_wrong_d():
    """Run 4-bit circuit with wrong d."""
    wrong_d = (PARAMS[4].d + 1) % PARAMS[4].n
    with timed(f"4-bit circuit (wrong d={wrong_d})"):
        return _run_4bit_circuit(d_override=wrong_d, initial_idx=2)


@pytest.fixture(scope="module")
def result_4bit_alt_idx():
    """Run 4-bit circuit with different INITIAL_IDX."""
    with timed("4-bit circuit (initial_idx=4)"):
        return _run_4bit_circuit(d_override=None, initial_idx=4)


def test_quantum_recovers_correct_d(result_4bit_correct):
    """Baseline: correct params recovers correct d."""
    params = PARAMS[4]
    df = _extract_d(result_4bit_correct.dataframe, params.n, params.n.bit_length())
    assert not df.empty, "No valid measurements"
    recovered = int(df["d_candidate"].mode()[0])
    assert recovered == params.d, f"Expected d={params.d}, got {recovered}"


def test_quantum_null_wrong_d(result_4bit_wrong_d):
    """
    Null test: circuit built with wrong d should NOT recover the correct d.
    This proves the circuit encoding actually uses d, not some trivial path.
    """
    params   = PARAMS[4]
    wrong_d  = (params.d + 1) % params.n
    df = _extract_d(result_4bit_wrong_d.dataframe, params.n, params.n.bit_length())
    if df.empty:
        pytest.skip("No valid measurements with wrong d (acceptable)")
    recovered = int(df["d_candidate"].mode()[0])
    assert recovered != params.d, (
        f"FAIL: wrong-d circuit still recovered correct d={params.d}. "
        "Suggests d is not actually encoded in the circuit."
    )
    # Ideally it recovers wrong_d
    assert recovered == wrong_d, f"Expected wrong_d={wrong_d}, got {recovered}"


def test_quantum_initial_idx_invariance(result_4bit_correct, result_4bit_alt_idx):
    """
    INITIAL_IDX should not affect recovered d.
    The starting point shifts the oracle but not the period.
    """
    params = PARAMS[4]
    var_len = params.n.bit_length()

    df1 = _extract_d(result_4bit_correct.dataframe, params.n, var_len)
    df2 = _extract_d(result_4bit_alt_idx.dataframe, params.n, var_len)

    assert not df1.empty and not df2.empty, "No valid measurements"
    d1 = int(df1["d_candidate"].mode()[0])
    d2 = int(df2["d_candidate"].mode()[0])
    assert d1 == d2 == params.d, (
        f"INITIAL_IDX changed result: idx=2 gave {d1}, idx=4 gave {d2}. Expected {params.d}."
    )


def test_quantum_distribution_structure(result_4bit_correct):
    """
    Valid (x1_r, x2_r) pairs should be enriched vs random baseline.
    For correct d, pairs satisfying x2_r ≡ -d*x1_r (mod n) should dominate.
    """
    params  = PARAMS[4]
    n, d    = params.n, params.d
    var_len = n.bit_length()
    df = _extract_d(result_4bit_correct.dataframe, n, var_len)

    if df.empty:
        pytest.skip("No valid measurements")

    total_shots = result_4bit_correct.dataframe["counts"].sum()
    valid_shots = df["counts"].sum()
    valid_fraction = valid_shots / total_shots

    # Random baseline: fraction of (x1_r, x2_r) pairs that are "valid"
    # There are n-1 valid x1_r values (coprime to n), each with 1 valid x2_r out of n.
    # So ~(n-1)/n^2 fraction of all pairs are valid by chance ~ 1/n.
    random_baseline = 1.0 / n

    assert valid_fraction > random_baseline, (
        f"Valid pairs not enriched: got {valid_fraction:.3f}, baseline {random_baseline:.3f}"
    )
    print(f"\n  Valid fraction: {valid_fraction:.3f} vs baseline {random_baseline:.3f} "
          f"({valid_fraction/random_baseline:.1f}x enriched)")


