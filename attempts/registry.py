# Registry: maps bit size → list of working attempts (oldest first).
# The last entry per bit size is considered "latest" and is what tests run.
# Never remove entries — append only.

LATEST = {
    4: [
        {"attempt": "attempt_002B_2026-03-29_1235", "expected_seconds": 15},
        {"attempt": "attempt_003_2026-03-29_1420", "expected_seconds": 60},
        {"attempt": "attempt_004_2026-03-29_1600", "expected_seconds": 25},  # ✅ verified: d=6
    ],
    6: [
        {"attempt": "attempt_002B_2026-03-29_1235", "expected_seconds": 60},
        {"attempt": "attempt_003_2026-03-29_1420", "expected_seconds": 120},
        {"attempt": "attempt_004_2026-03-29_1600", "expected_seconds": 25},  # ✅ verified: d=18
    ],
    7: [
        {"attempt": "attempt_004_2026-03-29_1600", "expected_seconds": 50},  # ✅ verified: d=56 (3212 CX — simulator only)
    ],
}
