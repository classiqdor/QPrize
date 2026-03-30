# Synthesis Results

One row per synthesis run. Add a row each time you run `solve()` and record the result.

| Attempt | Bits | Width | Depth | CX | Success |
|---------|------|-------|-------|----|---------|
| attempt_001_2026-03-29_1212 | 4 | — | — | — | ❌ (abandoned — naive x,y coords, obsolete) |
| attempt_002_2026-03-29_1230 | 4 | — | — | 716 | ✅* |
| attempt_002B_2026-03-29_1235 | 4 | 11 | — | 716 | ✅* |
| attempt_002B_2026-03-29_1235 | 6 | 16 | — | 1,252 | ✅* |
| attempt_003_2026-03-29_1420 | 4 | 11 | — | 716 | ✅* |
| attempt_003_2026-03-29_1420 | 6 | 16 | — | 1,252 | ✅* |
| attempt_004_2026-03-29_1507 | 4 | — | — | — | ❌ (unverified — EC arithmetic oracle, never ran to completion) |
| attempt_004_2026-03-29_1600 | 4 | 11 | — | 716 | ✅ |
| attempt_004_2026-03-29_1600 | 6 | 16 | — | 1,252 | ✅ (sim only) |
| attempt_004_2026-03-29_1600 | 7 | — | — | 3,212 | ✅ (sim only) |
| attempt_005_2026-03-29_truncated_varlen | 6 (var_len=4) | 14 | — | 1,022 | ❌ (QFT peaks fold — N=16 < n=31) |
| attempt_005_2026-03-29_truncated_varlen | 6 (var_len=3) | 12 | — | 778 | ❌ (QFT peaks fold — N=8 < n=31) |
| attempt_006_2026-03-29_ec_coords | 4 | 28 | — | 129,938 | ❌ (synthesized OK, execution timed out after 68 min — SIGKILL) |
| attempt_004B_2026-03-29_1900 | 4 | 11 | 1050 | 716 | ✅ (d=6) |
| attempt_004B_2026-03-29_1900 | 6 | 16 | 1271 | 1,252 | ✅ (d=18) |
| attempt_006B_2026-03-29_1900 | 4 | — | — | — | not yet run |
| attempt_007_2026-03-29_1840 | 4 | — | — | — | (pending — coordinate encoding, Kaliski inverse) |
| attempt_008_2026-03-29_1859 | 4 | — | — | — | (pending — coordinate encoding, Kaliski inverse, named QNum vars) |

\* Oracle was later found to be circular (encoded `neg_q_step = (n-d) % n` — required knowing `d` in advance).
  Returned the correct `d` but did not constitute a valid solution to ECDLP.
