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
   pip install classiq
   ```

2. Authenticate with Classiq:
   ```python
   import classiq; classiq.authenticate()
   ```

## Running

```bash
python solution.py 4      # 4-bit (synthesizes in ~9 min, runs on Classiq simulator)
```

## Path to full scalability

Two changes would make this solution fully scalable to cryptographic key sizes:

### 1. Replace `modular_inverse_lookup` with Kaliski's algorithm

Current (not scalable — O(p) table):
```python
@qperm
def modular_inverse_lookup(x: Const[QNum], result: QNum) -> None:
    inv_table = lookup_table(lambda v: pow(int(v), -1, p) ..., x)
    result ^= subscript(inv_table, x)
```

Scalable replacement using Classiq's built-in Kaliski modular inverse:
```python
@qperm
def scalable_modular_inverse(x: QNum, result: QNum) -> None:
    modular_inverse_inplace(p, x)   # Kaliski algorithm — O(p_bits²) gates
    inplace_xor(x, result)
    modular_inverse_inplace(p, x)   # uncompute
```

Cost: O(p_bits²) CX gates vs O(p) table entries. For p=13 (4-bit): negligible difference.
For p ≈ 2²⁵⁶: the difference between feasible and impossible.

### 2. Replace `sq_lookup` with `modular_square`

Current (not scalable — O(p) table):
```python
@qperm
def sq_lookup(a: Const[QNum], result: QNum) -> None:
    tbl = lookup_table(lambda av: (int(av) ** 2) % p, a)
    result ^= subscript(tbl, a)
```

Scalable replacement — use Classiq's built-in directly:
```python
modular_square(p, slope, t0)
```

This was the baseline in `attempt_example_ec`. It costs ~2,852 CX at p=13 vs 120 CX
for the lookup — a deliberate tradeoff to reduce gate count on the simulator. At
cryptographic scale, arithmetic is the only viable option.

### Expected cost at full scalability

For a 256-bit key (p ≈ 2²⁵⁶, p_bits=256):
- Kaliski inverse: O(p_bits²) ≈ O(65,536) gates per call
- `modular_multiply`: O(p_bits²) ≈ O(65,536) gates per call
- Per `ec_point_add`: ~6 multiplies + 2 inverses ≈ O(500k) gates
- Full circuit (2×var_len=512 additions): O(256M) CX gates

This is consistent with published estimates (Roetteler et al. 2017: ~2,330 logical qubits
and ~2.09×10⁹ Toffoli gates for 256-bit ECDLP). Hardware capable of running this does
not yet exist.

## Algorithm reference

- Roetteler, Naehrig, Svore, Lauter — *Quantum Resource Estimates for Computing
  Elliptic Curve Discrete Logarithms* (2017) — https://eprint.iacr.org/2017/598.pdf
- Haner, Jaques, Naehrig, Roetteler, Soeken — *Improved Quantum Circuits for Elliptic
  Curve Discrete Logarithms* (2020) — https://eprint.iacr.org/2020/077.pdf
