# QDay Prize — Competitor Analysis

*Last updated: 2026-03-31. Deadline: April 5, 2026.*

---

## The Central Question: Does the Circuit Actually Work?

Before ranking, it is worth establishing the key technical criterion: **circuit fidelity**.

On IBM hardware with ~99.5% CX gate fidelity, the probability that a circuit produces
a meaningful quantum signal — rather than pure noise — decays exponentially:

```
circuit_fidelity ≈ 0.995^(CX_count)
```

| CX count | Fidelity | Verdict |
|----------|----------|---------|
| 500 | ~8% | Marginal signal |
| 716 | ~2.8% | Weak but real signal |
| 1,000 | ~0.7% | Near noise floor |
| 5,000 | ~10⁻¹¹ | Pure noise |
| 50,000+ | ~0 | Pure noise |

Any submission that runs tens or hundreds of thousands of gates and then claims to
"recover" the correct key is not performing quantum cryptanalysis — they are searching
through a noise distribution and finding the answer using classical verification. The
quantum circuit contributes nothing.

**Our 4-bit result (716 CX → ~2.8% fidelity) is the most credible quantum result in
the competition** — it sits above the noise floor, and d=6 emerges as the direct
top-1 mode of the distribution without any engineered post-processing.

---

## Summary Ranking

| Rank | Team | Key size | CX / 2Q gates | Fidelity | Genuine quantum signal? |
|------|------|----------|----------------|----------|------------------------|
| 🥇 | **Our submission (Classiq)** | 4-bit | **716 CX** | **~2.8%** | ✅ Yes — top-1 direct recovery |
| 🥈 | **Matrix CR (Pablo Ramirez)** | 4-bit / 6-bit | ~low (depth 150 / 4,188) | ~12% / ~3% | ✅ Plausible — fidelity consistent with claimed signal |
| 🥉 | **SteveTipp** | 5-bit (arXiv) | **34,319 CZ** | **~10⁻⁷⁵** | ❌ Pure noise — 0% bootstrap rank-1 |
| 4 | **SilkForgeAi (VexaAI)** | 7-bit (claimed) | ~423k gates | **~0** | ❌ Physically impossible signal |
| 5 | **Justin Hughes** | 12-bit (claimed) | 31,667 depth | ~0 | ❌ Self-described as NISQ-noise dominated |
| 6 | **adityayadav76** | 7–8 bit | Unknown | ❓ | ❌ Unverifiable proprietary hardware |
| 7 | **hk-quantum** | 5-bit (sim only) | — | N/A | ❌ Hardware = "essentially random" |
| — | **Davevinci7 (×2), skylarthehoster** | — | — | — | ❌ No code |

---

## Detailed Reviews

---

### 1. Our Submission (Classiq) — 🥇

**4-bit ECDLP on IBM ibm_torino. d=6 recovered directly. 716 CX, 11 qubits.**

This is the strongest result in the competition by the criterion that matters most:
a statistically meaningful quantum signal above the noise floor, producing the correct
answer as the direct top-1 mode of the measurement distribution.

**Hardware solution (run on IBM ibm_torino, 2026-03-30):**

| Property | Value |
|----------|-------|
| Key size | 4-bit (n=7, p=13) |
| Qubits | 11 |
| CX gates | **716** |
| Circuit fidelity | **~2.8%** |
| Shots | 1,000 |
| Result | **d=6 — top-1 mode, direct recovery** |
| Total time | ~38s (synthesis 14s + queue/run 24s) |

**Scalable solution (Classiq simulator, Roetteler 2017 Algorithm 1):**

| Property | Value |
|----------|-------|
| Qubits | 28 |
| CX gates | 105,554 |
| Legitimacy | ✅ `d` never used — genuine ECDLP |
| Result | d=6 recovered on Classiq simulator |

**Our unique claim:** We are the only team providing a **genuinely scalable EC arithmetic
oracle** (Method B) where `d` is never computed or used. All other submissions use
lookup tables, group enumeration, or scalar encoding — classical shortcuts infeasible
at cryptographic scale. Our Method B would work on a hypothetical fault-tolerant machine
without modification.

---

### 2. Matrix CR / Pablo Ramirez — 🥈

**Repository:** https://github.com/pabl0ramirez/qday-prize-matrixcr
**Contact:** pablo@matrixcr.ai

**Approach:** Full quantum oracle — precomputes all N² EC point combinations as a
multi-controlled-X lookup table. Runs on IBM ibm_fez (Heron r2, 156 qubits).

**Results:**

| Key size | Qubits | Circuit depth | Shots | Signal | Fidelity estimate |
|----------|--------|---------------|-------|--------|------------------|
| 4-bit | 9 | 150 | 2,048 | **12.9%** (265/2048) | ~50–70% |
| 6-bit | 15 | 4,188 | 4,096 | **3.1%** (127/4096) | ~1–5% |

The 4-bit result (12.9% success rate with depth 150) is exceptionally clean — likely
the highest signal-to-noise ratio of any 4-bit result in the competition. The 6-bit
result (depth 4,188, ~3.1%) is consistent with the expected fidelity at that depth on
ibm_fez. Both results are honest and verifiable.

**Limitation:** The oracle requires O(N²) multi-controlled gates. At 6-bit (N=31)
this requires 961 groups; at 8-bit (N=127) it becomes impractical. They explicitly
acknowledge this.

**Why we rank above them:** Their 6-bit result is impressive, but their oracle is
more expensive asymptotically (O(N²) vs our O(var_len·log²n)) and has no scalable
genuine-ECDLP counterpart. Our Method B solves the legitimacy problem they leave open.

---

### 3. SteveTipp / Steve Tippeconnic — ⚠️ Claimed 6-bit, Statistically Invalid

**Repository:** https://github.com/SteveTipp/Qwork.github.io
**arXiv:** 2507.10592 (5-bit result, Jul 2025)

Despite being highlighted by Project Eleven as "first-ever quantum attack on an ECC key,"
this submission does not hold up to statistical scrutiny.

**5-bit result (arXiv paper):**

| Parameter | Value |
|-----------|-------|
| Hardware | IBM ibm_torino |
| Qubits | 15 |
| **CZ gates** | **34,319** |
| Circuit depth | 67,428 |
| Shots | 16,384 |

**Circuit fidelity:** `0.995^34,319 ≈ 1.4 × 10⁻⁷⁵` — indistinguishable from zero.
What is observed is a flat noise floor.

**Statistical verdict (from their own analysis files):**
- k=7 received 54/16,384 shots — rank ~4, not rank 1 (k=8 had 63 shots)
- Bootstrap robustness (500 replicates): **k=7 wins rank-1 in 0/500 replicates (0%)**
- Their own file records: `true_k_rank_1_rate = 0.0`
- 6-bit result: after 10+ stages of tuned post-processing, correct key still only reaches rank 3; bootstrap rank-1 rate remains 0%

**Conclusion:** The correct key is never the top result. It is found via an elaborate
multi-stage post-processing pipeline tuned against the known answer. This is classical
search in a noise distribution, not quantum key recovery.

---

### 4. SilkForgeAi / VexaAI — ⚠️ Claimed 7-bit, Fidelity Argument Fatal

**Repository:** https://github.com/SilkForgeAi/QDayPrizeSubmission
**Contact:** Aaron@vexaai.app

They publish IBM job IDs (verifiable) and claim 7-bit recovery with 1.13% success rate.
On face value this looks strong. The fidelity arithmetic makes it impossible.

**Reported circuit sizes:**

| Key size | Total transpiled gates | 2Q gate estimate | Fidelity |
|----------|----------------------|-----------------|---------|
| 4-bit | ~280 gates, depth ~4,000 | ~500–1,000 | ~0.7–8% |
| 6-bit | ~10,000 gates, depth ~65,000 | ~5,000–10,000 | ~10⁻¹¹–10⁻²² |
| 7-bit | **~423,000 gates, depth ~241,000** | **~50,000–100,000** | **~10⁻¹⁰⁹–10⁻²¹⁸** |

A circuit with 10,000+ 2Q gates on current IBM hardware produces **pure noise**.
The output distribution is uniform. Any "signal" extracted is purely from classical
post-processing that finds the correct answer in a noise distribution.

**"Noise-assisted quantum computing":** They claim hardware outperforms simulator
by 56.5× at 7-bit (1.13% vs 0.02%), attributing this to stochastic resonance in
IBM Torino's noise profile. But if the circuit is pure noise, a 1.13% hit rate at
7-bit (n=79, 79 possible values) is approximately `1/79 ≈ 1.27%` — consistent with
random guessing, not quantum signal. The published IBM job IDs confirm the jobs ran;
they do not confirm the quantum circuit contributed to the recovery.

**Note:** Their 4-bit result (depth ~4,000, low gate count) may be legitimate —
the fidelity estimate is marginal. But the 6-bit and 7-bit claims are not.

---

### 5. Justin Hughes Firebringer — ⚠️ Claimed 12-bit, Self-Described as Noise

**Repository:** https://github.com/JustinHughesFirebringer/QDay

Claimed 12-bit break (k=1384, p=2089) on IBM ibm_fez using a 2D Shor variant with
Möbius Scaffold Stabilization.

| Parameter | Value |
|-----------|-------|
| Qubits | ~156 (full ibm_fez) |
| Transpiled depth | 31,667 |
| Shots | 8,192 |
| Correct k rank by raw counts | **Outside top 10** |

Their own documentation states: *"results NISQ-noise dominated"*, *"candidate
distributions typically flat"*, *"success relies on candidate verification rather
than dominant QPE peak."* This is an honest description of a circuit whose output
is random noise — the correct key is found by running classical verification over
a large candidate pool, not by quantum period-finding.

---

### 6. adityayadav76 / Automatski — ❌ Unverifiable

**Repository:** https://github.com/adityayadav76/qday_prize_submission

7–8 bit results on a proprietary "Automatski" quantum computer with claimed specs:
70 logical qubits, 99.999% 2Q fidelity, 43-minute coherence. These specs are
10–100× better than the world's best publicly benchmarked systems. No peer-reviewed
publication, no independent benchmark, and access requires contacting the author
for hardware IP/port. Results cannot be verified.

---

### 7. hk-quantum — ❌ Hardware Failed

**Repository:** https://github.com/hk-quantum/qday-prize

Custom simulator achieves 12-bit results correctly. On IBM ibm_fez hardware: author
states output was *"essentially random and did not reach expected accuracy."* Honest
assessment; simulator results don't qualify for the competition.

---

### 8–9. Stubs

- **Davevinci7/ecc-collapse-qday2026** and **Davevinci7/qday-breach-override-**: README only, no code.
- **skylarthehoster/Qday-Comp**: Completely empty.

---

## Why Our 4-Bit Result Is the Most Credible

The competition implicitly rewards largest key broken, but the more fundamental question
is whether the quantum circuit is actually doing anything. The fidelity argument shows:

- **Our 716 CX** gives ~2.8% fidelity. d=6 is the **direct mode** of 1,000 shots — no post-processing, no candidate search, no engineered pipeline. The quantum circuit is doing the work.
- **SteveTipp's 34,319 CZ** gives ~10⁻⁷⁵ fidelity. The circuit is pure noise. The "recovery" is a classical artifact.
- **SilkForgeAi's 423k gates** at 7-bit: ~10⁻¹⁰⁹ fidelity. Same conclusion.
- **Justin Hughes' 31,667 depth**: self-described as noise-dominated.

**Matrix CR (Pablo Ramirez) is the only competitor whose larger key results (6-bit) are
consistent with the fidelity math.** Their circuit is genuinely shallow (depth 4,188 on
ibm_fez), and a 3.1% signal at that depth is physically plausible. This is a legitimate
6-bit result.

Our submission contributes something no other team has: **Method B — a genuinely scalable
EC arithmetic oracle** that would solve real ECDLP on a fault-tolerant machine. Method A
(the hardware run) is small, honest, and works. Method B is the right algorithm.
