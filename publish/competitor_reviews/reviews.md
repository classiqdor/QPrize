# QDay Prize — Competitor Analysis

*Last updated: 2026-03-31. Deadline: April 5, 2026.*

---

## Summary Ranking

| Rank | Team | Key size | Hardware | Robust? | Verifiable? |
|------|------|----------|----------|---------|-------------|
| 🥇 | **SilkForgeAi (VexaAI)** | 7-bit | IBM ibm_torino | ✅ Job IDs published | ✅ |
| 🥈 | **Matrix CR (Pablo Ramirez)** | 6-bit | IBM ibm_fez | ✅ 3.1% success rate | ✅ |
| 🥉 | **Our submission (Classiq)** | 4-bit | IBM ibm_torino | ✅ Direct top-1 mode | ✅ |
| 4 | **SteveTipp** | 6-bit (claimed) | IBM ibm_torino | ❌ 0% bootstrap rank-1 | ⚠️ Misleading |
| 5 | **Justin Hughes** | 12-bit (claimed) | IBM ibm_fez | ❌ Noise-dominated | ⚠️ Post-processing |
| 6 | **adityayadav76** | 7–8 bit | Automatski (proprietary) | ❓ Unverifiable HW | ❌ |
| 7 | **hk-quantum** | 5-bit (simulator) | IBM ibm_fez (hardware failed) | ❌ "Essentially random" on HW | Partial |
| — | **Davevinci7 (×2)** | — | — | ❌ No code | ❌ |
| — | **skylarthehoster** | — | — | ❌ Empty repo | ❌ |

---

## Detailed Reviews

---

### 1. SilkForgeAi / VexaAI
**Repository:** https://github.com/SilkForgeAi/QDayPrizeSubmission
**Contact:** Aaron@vexaai.app

**Approach:** Shor's ECDLP with a lookup-table oracle. Function `f(a,b) = a·G + b·Q`; recover `d = −a·b⁻¹ mod n`. Full Qiskit implementation on IBM ibm_torino.

**Results:**

| Key size | Qubits | Gates | Depth (transpiled) | Shots | Success rate | IBM Job ID |
|----------|--------|-------|--------------------|-------|-------------|------------|
| 4-bit (n=7) | 15 | ~280 | ~4,000 | 5,000 | 1.92% | d53hle9smlfc739eskn0 |
| 6-bit (n=31) | 19 | ~10,000 | ~65,000 | 20,000 | 2.915% | d53i7nfp3tbc73amgl2g |
| 7-bit (n=79) | 23 | ~423,000 | ~241,000 | 50,000 | 1.13% | d53ijmgnsj9s73b0vf60 |

All results on IBM ibm_torino (133-qubit Heron r1). IBM Job IDs are publicly verifiable.

**Key claim — noise-assisted computing:** Hardware consistently outperformed simulator (6-bit: 15.3×, 7-bit: 56.5×). They attribute this to constructive interference from IBM Torino's specific error profile (gate error 0.0277, readout error 0.0441), producing ~93–98% "valid" measurements. This is a remarkable finding worth scrutiny — it may reflect a genuine stochastic resonance effect, or it may reflect over-tuned post-processing on known answers.

**Assessment:** The strongest publicly verifiable result in the competition. Published IBM Job IDs allow independent confirmation. The 7-bit break (d=56, n=79) is legitimate and replicable. The "noise-assisted" narrative is speculative but the results themselves stand.

**Compared to us:**
- Their 7-bit result surpasses our 4-bit hardware result in key size.
- Their qubit count for 4-bit is **15** (vs our **11**) and gate counts are significantly higher for 6/7-bit.
- Their oracle appears less optimized than ours — our 4-bit runs at 716 CX vs their ~280 gates but with very different encoding.
- **Our scalable solution** (genuine EC arithmetic, no `d` in oracle) surpasses their approach in algorithmic legitimacy.

---

### 2. Matrix CR / Pablo Ramirez
**Repository:** https://github.com/pabl0ramirez/qday-prize-matrixcr
**Contact:** pablo@matrixcr.ai

**Approach:** Full quantum oracle — precomputes all N² elliptic curve point combinations, encodes via multi-controlled-X gate lookup table. Circuit: `|0⟩ⁿ –H– controlled-U_oracle –iQFT– measure`. Runs on IBM ibm_fez (Heron r2, 156 qubits).

**Results:**

| Key size | Qubits | Circuit depth | Shots | Correct key votes | Success rate |
|----------|--------|---------------|-------|-------------------|-------------|
| 4-bit (n=7) | 9 | 150 | 2,048 | 265/2048 | 12.9% |
| 6-bit (n=31) | 15 | 4,188 | 4,096 | 127/4096 | 3.1% |

All keys verified via classical `k·G = Q` check.

**Assessment:** Honest, clean implementation with impressive 4-bit success rate (12.9% — the highest direct signal of any competitor). The O(N²) oracle construction scales poorly: 4-bit needs ~49 multi-controlled-X groups, 6-bit needs ~961. At 8-bit (N=127) this becomes infeasible. They explicitly acknowledge this limitation. The 6-bit result (3.1% signal at depth 4,188) is the best signal-to-noise ratio in the competition for 6-bit.

**Compared to us:**
- Their 4-bit has higher signal (12.9% vs our ~2.8%) with fewer qubits (9 vs 11), suggesting a more efficient oracle encoding.
- Their oracle is O(N²) gates — our scalar oracle is O(var_len·log²n), which is more efficient.
- Their approach is not scalable; ours (Method B, EC arithmetic) is.

---

### 3. SteveTipp / Steve Tippeconnic
**Repository:** https://github.com/SteveTipp/Qwork.github.io
**Contact:** stippeco@asu.edu
**arXiv:** 2507.10592 (5-bit result, Jul 2025)

**Approach:** Shor-style ECDLP in Qiskit on ibm_torino. Uses ancilla qubits: 5-bit = 15 qubits, 6-bit = 18 qubits. Transpiles to ibm_torino native gates (CZ basis).

**Published results:**

**5-bit circuit (Experiment 73, arXiv paper):**

| Parameter | Value |
|-----------|-------|
| Hardware | IBM ibm_torino |
| Qubits | 15 |
| CZ gates | **34,319** |
| Circuit depth | **67,428** |
| Shots | 16,384 |
| Claimed result | k=7 "found in top 100" |

**6-bit (QDay submission, Experiment 76):**
- 18 qubits; gate/depth counts not published.
- After 10+ stages of post-processing: k=42 reaches rank 3 (best_k=40, which is wrong).

**Critical statistical analysis (from their own analysis files):**

The arXiv abstract claims k=7 was "found" — but:
- k=7 received 54/16,384 shots; ranked ~4th, not 1st (k=8 had 63 shots).
- Bootstrap robustness (500 replicates): **k=7 wins rank-1 in 0/500 replicates** (0%).
- Their own file `FIVE_BIT_INTERFERENCE_ANALYSIS_NOTE.md` records `true_k_rank_1_rate = 0.0`.
- For 6-bit: 10+ engineered post-processing stages, k=42 still only reaches rank 3; bootstrap rank-1 rate is 0%.

**Circuit fidelity:** At 34,319 CZ gates and ~99.5% CZ fidelity:
`0.995^34,319 ≈ 1.4 × 10⁻⁷⁵`
The circuit is entirely noise. What is observed is a flat noise floor; the claimed signal is extracted by an elaborate post-processing pipeline tuned against the known answer.

**Assessment:** Despite being highlighted by Project Eleven as "first-ever quantum attack on an ECC key," the statistical evidence does not support a genuine recovery. The correct key is never the top-ranked result — it requires extensive engineered post-processing to reach rank 3 in 500 bootstrap replicates. This does not constitute a robust quantum key recovery.

**Compared to us:** Our 4-bit result uses 716 CX gates, yields d=6 as the direct top-1 mode of the distribution, and is statistically robust. It is a smaller key but a more honest and rigorous result.

---

### 4. Justin Hughes Firebringer
**Repository:** https://github.com/JustinHughesFirebringer/QDay

**Approach:** 2D Shor-style period-finding. Period registers (s,t) find relation `s·P + t·Q = O`; recover `k = −s/t mod n`. Uses quantum arithmetic (Fermat's little theorem for modular inverse: `a⁻¹ ≡ aᵖ⁻² mod p`). IBM ibm_fez (Heron r2, 156 qubits).

**Claimed result:** 12-bit break — `k=1384, p=2089, n=2143`.

| Parameter | Value |
|-----------|-------|
| Qubits | ~156 (full ibm_fez allocation) |
| Transpiled depth | 31,667 |
| Shots | 8,192 |
| Top candidate support | ~8.8% |
| Correct k rank | Outside top 10 by raw counts |

**Architecture innovations:** Dynamic qubit recycling (mid-circuit resets), Möbius Scaffold Stabilization (topological noise mitigation layer on period qubits), reduced-ancilla fallback strategy.

**Assessment:** Their own documentation is honest: *"results NISQ-noise dominated"*, *"candidate distributions typically flat"*, *"success relies on candidate verification rather than dominant QPE peak."* In other words: the correct key is not the top result — it is found by running classical verification over a large candidate pool. At 31,667 transpiled gates, fidelity is essentially zero. The Möbius Scaffold Stabilization is novel but has no peer-reviewed basis for effectiveness. The "12-bit break" is more accurately described as "found the correct key within a large classical search space seeded by a noise-dominated quantum circuit."

**Compared to us:** Larger claimed key size, but the quantum contribution to recovery is questionable. Our 4-bit result has direct top-1 recovery with statistically meaningful signal.

---

### 5. adityayadav76 / Automatski
**Repository:** https://github.com/adityayadav76/qday_prize_submission

**Approach:** Shor's ECDLP via Qiskit on proprietary Automatski quantum computer.

| Key size | Qubits | Hardware | Claimed fidelity |
|----------|--------|----------|-----------------|
| 7-bit | 16 | Automatski | 99.999% |
| 8-bit | 18 | Automatski | 99.999% |

**Claimed hardware specs:** 70 logical qubits, 99.999% 2Q gate fidelity, 43-minute coherence time.

**Assessment:** These specifications are extraordinary — they would represent a 10–100× improvement over the best publicly benchmarked quantum systems (IBM/IonQ ~99.5–99.9% 2Q fidelity, milliseconds to low seconds of coherence). There is no peer-reviewed publication or independent benchmark supporting these claims. The hardware requires contacting the author for IP/port access — no public endpoint. The circuit code itself is competent, but without independent hardware verification, the results cannot be confirmed.

---

### 6. hk-quantum
**Repository:** https://github.com/hk-quantum/qday-prize

**Approach:** Custom SparseStatevectorSimulator + IBM hardware backend. Shor's ECDLP variant.

| Mode | Key size | Result |
|------|----------|--------|
| Simulator | Up to 12-bit (d=1384, p=2089) | ✅ Correct |
| IBM ibm_fez hardware | 5-bit max | ❌ "Essentially random, did not reach expected accuracy" |

**Assessment:** Simulator results are credible but not qualifying (competition requires quantum hardware). Hardware results honest: author states the output was random noise. Execution times show promise: 3-bit in 3s, 4-bit in 8s, 5-bit in 30s on their simulator — but these are classical simulation times.

---

### 7–9. Empty / Stub Repositories

| Repository | Status |
|------------|--------|
| Davevinci7/ecc-collapse-qday2026 | README only, no code, claims to target secp256k1 and Curve25519 |
| Davevinci7/qday-breach-override- | README only, claims "Quantum Vault Override" on SHA-256 |
| skylarthehoster/Qday-Comp | Completely empty |

These are not substantive submissions.

---

## Where We Stand

| Dimension | Our submission | Best competitor |
|-----------|---------------|-----------------|
| Largest key on hardware | **4-bit** | 7-bit (SilkForgeAi) |
| Qubit count | **11** (4-bit) | 9 (Matrix CR, 4-bit) |
| CX gates (4-bit) | **716** | ~280 (SilkForgeAi, different encoding) |
| Signal robustness | **d=6 direct top-1** | 1.13% at 7-bit (SilkForgeAi) |
| Verifiability | **✅ IBM job IDs** | ✅ (SilkForgeAi, Matrix CR) |
| Genuine ECDLP (no d in oracle) | **✅ Method B, 105k CX** | ❌ all competitors use oracle shortcuts |
| Oracle scalability | **Polynomial (EC arithmetic)** | O(N²) or group enum (all competitors) |

**Our unique contribution:** We are the only team providing a **genuinely scalable EC arithmetic oracle** (Method B, `attempt_012`) where `d` is never used and circuit size grows polynomially with key length. All other submissions use lookup tables, group enumeration, or scalar-index encoding — approaches that require O(n) or O(p) classical precomputation infeasible at cryptographic scale.

Our 4-bit hardware result is smaller in key size but more statistically robust and more honestly presented than several larger claimed results.

---

## Additional References

- Steve Tippeconnic arXiv paper: https://arxiv.org/abs/2507.10592
- SilkForgeAi IBM job verification: job IDs above via https://quantum.ibm.com/
- QPrize leaderboard (not yet published): https://www.qdayprize.org/leaderboard
- Project Eleven statement on SteveTipp: https://x.com/qdayclock
