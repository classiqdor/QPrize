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

- **`repos/classiq-library/`** — Open-source quantum algorithm library (gitignored)
- **`repos/qday-prize/`** — Original competition submission (gitignored)
- **`repos/Cadmium/`** — Classiq backend source (read-only reference, gitignored)

---

## classiq-library (repos/classiq-library)

### Install

```fish
cd repos/classiq-library
pip install -r requirements.txt -r requirements_tests.txt
pre-commit install
```

### Testing

```fish
./tests/wrap_pytest.sh tests/
```

Test config variants: `tests/config_quick_tests.ini` (fast), `tests/config_weekly.ini` (extended). Per-notebook timeout limits: `tests/resources/timeouts.yaml`.

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
- `repos/classiq-library/algorithms/number_theory_and_cryptography/elliptic_curves/elliptic_curve_discrete_log.ipynb`
- `repos/classiq-library/algorithms/number_theory_and_cryptography/discrete_log/discrete_log.ipynb`

---

## QPrize — Project Files

Key files in the root:
- `consts.py` — all competition curve parameters (bits 4–21), with field docs
- `utils.py` — `timed()` context manager, `play_ending_sound()`
- `ec.py` — classical EC point arithmetic (`point_add`)
- `attempts/` — quantum circuit attempts; `attempt_000` is a classical curve explorer
- `tests/` — pytest test suite (`pytest` from root runs all tests)
- `worklog/` — per-session activity logs

Shor's algorithm for ECDLP. See `PLAN.md` for current status and optimization roadmap.

| Variant | Bits | Qubits | CX gates | Status |
|---|---|---|---|---|
| Scalar oracle (002B–004) | 4 | 11 | 716 | ✅ Hardware-verified |
| Scalar oracle (002B–004) | 6 | 16 | 1,252 | Simulator only (~0.15% fidelity) |
| EC arithmetic oracle (004-1507) | 4 | TBD | TBD | Unverified |
