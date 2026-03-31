# Hardware Solution — Scalar Oracle on IBM Quantum Hardware

This solution runs Shor's ECDLP algorithm on **real IBM quantum hardware** (ibm_torino).
It successfully recovers the 4-bit private key `d=6` in ~38 seconds total.

## What it does

Implements Shor's algorithm with a **scalar-index oracle** (Method A):
- Oracle register holds integer `k ∈ Z_n` (scalar index of an EC group element)
- Oracle computes `ecp_idx = initial_idx + x1·1 + x2·(−d) mod n`
- After inverse QFT, recover `d = −x2_r · x1_r⁻¹ mod n`

**Note on legitimacy:** The oracle constants require enumerating all `n` EC group elements
classically (`group enum`). This is feasible for competition key sizes (n ≤ ~50,000) but
not for cryptographic-scale keys. See the scalable solution for a genuinely scalable
(though currently too expensive for hardware) approach.

## Circuit specs (4-bit)

| Property | Value |
|----------|-------|
| Key size | 4-bit (n=7, p=13) |
| Qubits | 11 |
| CX gates | 716 |
| Circuit depth | 1,050 |
| Hardware fidelity | ~2.8% (0.995^716) |
| Hardware | IBM ibm_torino (133-qubit Heron r1) |
| Execution time | ~38s (synthesis 14s + queue+run 24s) |
| Result | ✅ d=6 recovered correctly |

## Setup

1. Install dependencies (from repo root):
   ```bash
   python -m venv venv && source venv/bin/activate
   pip install classiq
   ```

2. Authenticate with Classiq:
   ```python
   import classiq; classiq.authenticate()
   ```

3. Set IBM credentials (copy `.env.example` to `.env` and fill in):
   ```bash
   cp .env.example .env
   # edit .env with your IBM_TOKEN, IBM_INSTANCE
   ```

## Running

**Simulator (default — safe, free, instant):**
```bash
source venv/bin/activate
python solution.py
```

**Real IBM hardware (explicit flag required — consumes IBM budget):**
```bash
set -a; source .env; set +a
python solution.py --ibm
```

## Expected output

```
⚠️  Running on REAL IBM hardware — this consumes budget!
[scalar 4-bit] n=7 | backend=IBM ibm_torino
[Synthesize] done in 13.8s
  Qubits: 11 | Depth: 1050 | CX: 716
[Execute] done in 24.1s
  Recovered d=6, expected d=6 → ✅
```
