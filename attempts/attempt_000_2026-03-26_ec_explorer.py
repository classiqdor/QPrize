# attempt_000 — 2026-03-26
# Manual / classical sanity check (no quantum).
#
# Run this script to visually verify the curve structure for any bit size:
#   python attempts/attempt_000_2026-03-26_ec_explorer.py        # 4-bit
#   python attempts/attempt_000_2026-03-26_ec_explorer.py 6      # 6-bit
#
# Prints every point k*G from k=1 to n, confirming:
#   - Q appears at k=d  (so Q = d*G is correct)
#   - n*G = point at infinity  (so n is the group order)
#
# This is the "pre-quantum" ground truth — if these don't match consts.py,
# something is wrong before we even write a circuit.

import sys
sys.path.insert(0, "..")

from consts import PARAMS
from ec import point_add


def explore(bits: int) -> None:
    params = PARAMS[bits]
    print(f"Curve: y^2 = x^3 + {params.b}  (mod {params.p})")
    print(f"Generator G = {params.G},  order n = {params.n}")
    print(f"Public key Q = {params.Q},  private key d = {params.d}  (Q should appear at d*G)\n")

    current = params.G
    print(f"1G = {current}  <-- G")
    for k in range(2, params.n + 1):
        current = point_add(current, params.G, params.p, params.a)
        note = ""
        if k == params.d:
            note = "  <-- Q = d*G  ✓" if current == params.Q else "  <-- MISMATCH with Q!"
        elif k == params.n:
            note = "  <-- point at infinity (n*G)"
        print(f"{k}G = {current}{note}")


if __name__ == "__main__":
    bits = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    explore(bits)
