# Synthesis Results

One row per synthesis run. Add a row each time you run `solve()` and record the result.

| Attempt | Bits | Width | Depth | CX | Success | Legitimacy |
|---------|------|-------|-------|----|---------|------------|
| attempt_001_2026-03-29_1212 | 4 | — | — | — | ❌ (abandoned) | `lookup inverse` |
| attempt_002_2026-03-29_1230 | 4 | — | — | 716 | ✅* | `d in oracle` |
| attempt_002B_2026-03-29_1235 | 4 | 11 | — | 716 | ✅* | `d in oracle` |
| attempt_002B_2026-03-29_1235 | 6 | 16 | — | 1,252 | ✅* | `d in oracle` |
| attempt_003_2026-03-29_1420 | 4 | 11 | — | 716 | ✅* | `d in oracle` |
| attempt_003_2026-03-29_1420 | 6 | 16 | — | 1,252 | ✅* | `d in oracle` |
| attempt_004_2026-03-29_1507 | 4 | — | — | — | ❌ (unverified — never ran to completion) | `lookup inverse` |
| attempt_004_2026-03-29_1600 | 4 | 11 | — | 716 | ✅ | `group enum` |
| attempt_004_2026-03-29_1600 | 6 | 16 | — | 1,252 | ✅ (sim only) | `group enum` |
| attempt_004_2026-03-29_1600 | 7 | — | — | 3,212 | ✅ (sim only) | `group enum` |
| attempt_005_2026-03-29_truncated_varlen | 6 (var_len=4) | 14 | — | 1,022 | ❌ (QFT peaks fold) | `group enum` |
| attempt_005_2026-03-29_truncated_varlen | 6 (var_len=3) | 12 | — | 778 | ❌ (QFT peaks fold) | `group enum` |
| attempt_006_2026-03-29_ec_coords | 4 | 28 | — | 129,938 | ❌ (execution timed out — SIGKILL after 68 min) | `lookup inverse` |
| attempt_004B_2026-03-29_1900 | 4 | 11 | 1050 | 716 | ✅ (d=6) | `group enum` |
| attempt_004B_2026-03-29_1900 | 6 | 16 | 1271 | 1,252 | ✅ (d=18) | `group enum` |
| attempt_006B_2026-03-29_1900 | 4 | — | — | — | not yet run | `lookup inverse` |
| attempt_007_2026-03-29_1840 | 4 | — | — | — | pending | `none` |
| attempt_008_2026-03-29_1859 | 4 | — | — | — | pending | `none` |
| attempt_example_scalar | 4 | 11 | 1050 | 716 | ✅ (d=6) | `group enum` |
| attempt_example_scalar | 6 | 17 | 3280 | 2,910 | ✅ (d=18) | `group enum` |
| attempt_011_2026-03-30_1210 | 4 | 26 | 226,377 | 136,106 | ✅ (d=6) | `none` |
| attempt_012_2026-03-30_1621 | 4 | 28 | 105,378 | 105,554 | ✅ (d=6) | `none` |

\* Oracle was later found to be circular (`neg_q_step = (n-d) % n` — `d` required in advance).
  Returned the correct `d` but did not constitute a valid solution to ECDLP.

---

### Legitimacy tag reference

| Tag | What it means | Why it doesn't scale |
|-----|--------------|----------------------|
| `d in oracle` | `d` baked directly into circuit constants | Circular — you need `d` to build the circuit that finds `d` |
| `group enum` | Oracle constants derived by iterating all n EC group elements to build a point→index table | O(n) classical work; for a 256-bit curve n ≈ 2²⁵⁶ |
| `lookup inverse` | `mock_modular_inverse` uses a precomputed table of all inverses mod p | O(p) memory; for a 256-bit prime p ≈ 2²⁵⁶ entries |
| ✅ `none` | No known shortcuts | Would work at cryptographic scale |
