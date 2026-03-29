# Classical elliptic curve arithmetic (no quantum).
# Curve equation: y^2 = x^3 + a*x + b  (mod p)
# Points are (x, y) tuples; None represents the point at infinity.

def point_add(P1, P2, p, a):
    """Return P1 + P2 on the curve y^2 = x^3 + a*x + b (mod p)."""
    if P1 is None: return P2
    if P2 is None: return P1
    x1, y1 = P1
    x2, y2 = P2
    if x1 == x2 and (y1 != y2 or y1 == 0):
        return None
    if P1 == P2:
        m = (3 * x1 ** 2 + a) * pow(2 * y1, -1, p)
    else:
        m = (y2 - y1) * pow(x2 - x1, -1, p)
    m %= p
    x3 = (m ** 2 - x1 - x2) % p
    y3 = (m * (x1 - x3) - y1) % p
    return x3, y3
