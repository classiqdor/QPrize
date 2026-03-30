from dataclasses import dataclass


class EllipticCurve:
    """y^2 = x^3 + a*x + b (mod p). Accepts EllipticCurve(params) or EllipticCurve(p, a, b)."""
    def __init__(self, params_or_p, a=None, b=None):
        if hasattr(params_or_p, "p"):
            self.p, self.a, self.b = params_or_p.p, params_or_p.a, params_or_p.b
        else:
            self.p, self.a, self.b = params_or_p, a, b


@dataclass
class Parameters:
    """
    Parameters for a competition ECC instance (curve y² = x³ + ax + b mod p).

    bits     — key size (the competition asks to break a `bits`-bit key)
    p        — prime field modulus; coordinates are integers mod p
    order_E  — total number of points on E(F_p), including point at infinity
    n        — order of the generator G; the discrete log d lives in Z_n
               (equals order_E when h=1, i.e. all competition curves are prime-order)
    h        — cofactor: h = order_E / n  (always 1 for these curves)
    G        — generator point as (x, y); public, defines the group
    d        — private key: the integer we want to find (Q = d·G)
    Q        — public key point: Q = d·G; given, do not use d to derive it
    a        — curve parameter a in y² = x³ + ax + b  (= 0 for all competition curves)
    b        — curve parameter b  (= 7 for all competition curves, same as secp256k1)
    """
    bits: int
    p: int
    order_E: int
    n: int
    h: int
    G: tuple
    d: int
    Q: tuple
    a: int = 0
    b: int = 7


PARAMS = {
    # Test curves (smaller p → faster synthesis for scalable coordinate attempts)
    3:  Parameters(bits=3,  p=7,       order_E=7,       n=7,       h=1, G=(3,  2),      d=3,     Q=(6,  5),  a=0, b=5),
    4:  Parameters(bits=4,  p=13,      order_E=7,       n=7,       h=1, G=(11, 5),      d=6,     Q=(11, 8)),
    6:  Parameters(bits=6,  p=43,      order_E=31,      n=31,      h=1, G=(34, 3),      d=18,    Q=(21, 25)),
    7:  Parameters(bits=7,  p=67,      order_E=79,      n=79,      h=1, G=(48, 60),     d=56,    Q=(52, 7)),
    8:  Parameters(bits=8,  p=163,     order_E=139,     n=139,     h=1, G=(112, 53),    d=103,   Q=(122, 144)),
    9:  Parameters(bits=9,  p=349,     order_E=313,     n=313,     h=1, G=(22, 191),    d=135,   Q=(138, 315)),
    10: Parameters(bits=10, p=547,     order_E=547,     n=547,     h=1, G=(386, 359),   d=165,   Q=(286, 462)),
    11: Parameters(bits=11, p=1051,    order_E=1093,    n=1093,    h=1, G=(471, 914),   d=756,   Q=(179, 86)),
    12: Parameters(bits=12, p=2089,    order_E=2143,    n=2143,    h=1, G=(1417, 50),   d=1384,  Q=(1043, 1795)),
    13: Parameters(bits=13, p=4159,    order_E=4243,    n=4243,    h=1, G=(3390, 2980), d=820,   Q=(3457, 3962)),
    14: Parameters(bits=14, p=8209,    order_E=8293,    n=8293,    h=1, G=(5566, 7),    d=137,   Q=(2144, 2381)),
    15: Parameters(bits=15, p=16477,   order_E=16693,   n=16693,   h=1, G=(15429, 10667), d=14794, Q=(6884, 12671)),
    16: Parameters(bits=16, p=32803,   order_E=32497,   n=32497,   h=1, G=(14333, 24084), d=20248, Q=(31890, 7753)),
    17: Parameters(bits=17, p=65647,   order_E=65173,   n=65173,   h=1, G=(12976, 52834), d=1441,  Q=(477, 58220)),
    18: Parameters(bits=18, p=131251,  order_E=130579,  n=130579,  h=1, G=(66566, 127721), d=26320, Q=(122895, 58382)),
    19: Parameters(bits=19, p=262153,  order_E=262567,  n=262567,  h=1, G=(44507, 141754), d=36124, Q=(253977, 23539)),
    20: Parameters(bits=20, p=525043,  order_E=524269,  n=524269,  h=1, G=(449655, 39077),  d=493247, Q=(417592, 204251)),
    21: Parameters(bits=21, p=1048783, order_E=1050337, n=1050337, h=1, G=(231634, 106125),  d=653735, Q=(1047961, 428633)),
}
