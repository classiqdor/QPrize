# Scalable Solution — Genuine EC Arithmetic Oracle (Roetteler 2017)

This solution implements **genuine ECDLP** using quantum EC arithmetic.
The private key `d` is never computed or used during circuit construction.
This is the scientifically correct approach — it would scale to large key sizes
if quantum hardware were powerful enough.

## What it does

Implements Shor's algorithm with an **EC coordinate oracle** (Method B):
- Oracle register holds an EC point `(x, y) ∈ F_p × F_p`
- Classical precomputation uses only `G` and `Q` as EC points (no `d`)
- Oracle computes `ecp = P0 + x1·G − x2·Q` using quantum EC arithmetic
- Implements Roetteler, Naehrig, Svore, Lauter (2017) Algorithm 1

**Legitimacy:** `d` is never used anywhere. Two non-scalable shortcuts remain:
- `modular_inverse_lookup` — lookup table of `x⁻¹ mod p`, size `p` entries
- `sq_lookup` — lookup table of `x² mod p`, size `p` entries

Both are feasible for small competition primes (p=13) but not for 256-bit cryptographic
keys (p ≈ 2²⁵⁶). Replacing them with Kaliski's modular inverse and schoolbook
arithmetic would make the circuit fully scalable.

## Circuit specs (4-bit)

| Property | Value |
|----------|-------|
| Key size | 4-bit (n=7, p=13) |
| Qubits | 28 |
| CX gates | 105,554 |
| Circuit depth | 105,378 |
| Hardware fidelity | ~0% (far below hardware viability) |
| Execution | Classiq simulator only |
| Result | ✅ d=6 recovered correctly (simulator) |

## Why it's expensive

Each EC point addition requires:
- 2× modular inverse (118 CX each)
- 4× modular multiply (2,527 CX each)
- 2× modular square replaced by sq_lookup (120 CX each)

Per addition: ~15,874 CX × 8 additions = ~105k total.

The bottleneck is `modular_multiply` (~2,527 CX each). Eliminating it —
via projective coordinates, schoolbook decomposition, or QROM lookup — is
the path to hardware viability.

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

## Running

```bash
source venv/bin/activate
python solution.py 4      # 4-bit (synthesizes in ~9 min, runs on Classiq simulator)
```

## Algorithm reference

- Roetteler, Naehrig, Svore, Lauter — *Quantum Resource Estimates for Computing
  Elliptic Curve Discrete Logarithms* (2017) — https://eprint.iacr.org/2017/598.pdf
- Haner, Jaques, Naehrig, Roetteler, Soeken — *Improved Quantum Circuits for Elliptic
  Curve Discrete Logarithms* (2020) — https://eprint.iacr.org/2020/077.pdf
