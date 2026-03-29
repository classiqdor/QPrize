# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Shell

The user's default shell is **fish**.

## Environment Variables

```fish
set -x CLASSIQ_REPO /home/dor/Sources/Classiq/claude_repos/classiq-library
set -x VENV /home/dor/Sources/Classiq/claude_repos/venv
```

## Venv

```fish
python -m venv $VENV
source $VENV/bin/activate.fish
```

Once activated, use plain `python`, `pip`, `jupyter`.

## Repository Structure

- **`classiq-library/`** — Open-source quantum algorithm library (100+ algorithms as Jupyter notebooks)
- **`qday-prize/`** — Competition submission: Shor's algorithm for elliptic curve discrete logarithm (ECDLP)

---

## classiq-library

### Install

```fish
pip install -r requirements.txt -r requirements_tests.txt
pre-commit install
```

### Testing

```fish
./tests/wrap_pytest.sh tests/
```

Test config variants: `tests/config_quick_tests.ini` (fast), `tests/config_weekly.ini` (extended). Per-notebook timeout limits: `tests/resources/timeouts.yaml`.

### Linting

```fish
pre-commit run --all-files
```

### Running Notebooks

```fish
jupyter nbconvert --to notebook --execute <notebook.ipynb> --output <output.ipynb>
```

Set these env vars to suppress browser popups from `show()`:

```fish
set -x BROWSER $CLASSIQ_REPO/.internal/update_outputs/fake_browser.sh
set -x OPENVSCODE some-dummy-value
```

### Reference Notebooks

Code is based primarily on:
- `algorithms/number_theory_and_cryptography/elliptic_curves/elliptic_curve_discrete_log.ipynb`
- `algorithms/number_theory_and_cryptography/discrete_log/discrete_log.ipynb`

---

## qday-prize

Shor's algorithm for ECDLP using **group-index encoding**: EC points as integers mod group order `n`, eliminating quantum modular inversion and reducing qubit count from O(log p) to O(log n).

| Variant | Bits | Qubits | CX gates | Status |
|---|---|---|---|---|
| Ripple-carry | 4 | 11 | 716 | Proven on hardware (Rigetti, IonQ, IBM) |
| QFT-space adder | 6 | 16 | 1,252 | Simulator only; hardware fidelity ~0.15% |

Key files: `solution/shor_ecdlp_classiq.py`, `solution/ecc_classical.py`, `process/log.md`.
