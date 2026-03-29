from consts import PARAMS


def mod_inverse(k, p):
    if k % p == 0:
        raise ZeroDivisionError
    return pow(k, -1, p)


def point_add(P1, P2, p, a):
    if P1 is None: return P2
    if P2 is None: return P1
    x1, y1 = P1
    x2, y2 = P2
    if x1 == x2 and (y1 != y2 or y1 == 0):
        return None
    if P1 == P2:
        m = (3 * x1**2 + a) * mod_inverse(2 * y1, p)
    else:
        m = (y2 - y1) * mod_inverse(x2 - x1, p)
    m %= p
    x3 = (m**2 - x1 - x2) % p
    y3 = (m * (x1 - x3) - y1) % p
    return x3, y3


if __name__ == "__main__":
    params = PARAMS[4]
    print(f"Curve: y^2 = x^3 + {params.b} (mod {params.p})")
    print(f"Calculating G up to {params.n}G...\n")

    current = params.G
    print(f"1G = {current}  <-- Generator (G)")

    for i in range(2, params.n + 1):
        current = point_add(current, params.G, params.p, params.a)
        note = ""
        if i == params.d:
            note = "  <-- Public Key (Q = d*G)"
        elif i == params.n:
            note = "  <-- Point at Infinity (n*G)"
        print(f"{i}G = {current}{note}")
