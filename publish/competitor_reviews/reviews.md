# QDay Prize — Competitor Analysis

*Last updated: 2026-03-31. Deadline: April 5, 2026.*

---

## Known Submissions

| Repository | Author | Key size | Hardware | Notes |
|------------|--------|----------|----------|-------|
| [SilkForgeAi/QDayPrizeSubmission](https://github.com/SilkForgeAi/QDayPrizeSubmission) | Aaron / VexaAI | 4, 6, 7-bit | IBM ibm_torino | Published IBM job IDs; 7-bit circuit fidelity is near zero |
| [pabl0ramirez/qday-prize-matrixcr](https://github.com/pabl0ramirez/qday-prize-matrixcr) | Pablo Ramirez / Matrix CR | 4, 6-bit | IBM ibm_fez | Full quantum oracle; clean signal at 4-bit |
| [SteveTipp/Qwork.github.io](https://github.com/SteveTipp/Qwork.github.io) | Steve Tippeconnic | 5-bit (arXiv), 6-bit (QDay) | IBM ibm_torino | arXiv: 2507.10592. Highlighted by Project Eleven — but see statistical analysis below |
| [JustinHughesFirebringer/QDay](https://github.com/JustinHughesFirebringer/QDay) | Justin Hughes | 12-bit (claimed) | IBM ibm_fez | Self-described as NISQ-noise dominated |
| [adityayadav76/qday_prize_submission](https://github.com/adityayadav76/qday_prize_submission) | Aditya Yadav / Automatski | 7–8 bit | Automatski (proprietary) | Reproducibility concern: requires contacting author for machine IP/port |
| [hk-quantum/qday-prize](https://github.com/hk-quantum/qday-prize) | hk-quantum | 12-bit (sim), 5-bit (HW) | IBM ibm_fez | Hardware results: "essentially random" — author's own assessment |
| [Davevinci7/ecc-collapse-qday2026](https://github.com/Davevinci7/ecc-collapse-qday2026) | Davevinci7 | — | — | README only, no code |
| [Davevinci7/qday-breach-override-](https://github.com/Davevinci7/qday-breach-override-) | Davevinci7 | — | — | README only, no code |
| [skylarthehoster/Qday-Comp](https://github.com/skylarthehoster/Qday-Comp) | skylarthehoster | — | — | Empty repository |

---

## Technical Framework: Circuit Fidelity

A useful lens for evaluating any NISQ result is **circuit fidelity** — the probability
that a circuit executes without a single error, approximated as:

```
fidelity ≈ 0.995^(2Q_gate_count)   (IBM hardware, ~99.5% per CX/CZ)
```

This decays rapidly. A circuit with thousands of 2Q gates produces output that is
dominated by noise, and any "signal" extracted from it is at risk of being a
post-processing artifact rather than a quantum result.

| 2Q gate count | Fidelity | Notes |
|---------------|----------|-------|
| ~75–150 | 50–70% | Strong signal |
| 716 | ~2.8% | Weak but meaningful signal |
| 1,000 | ~0.7% | Near noise floor |
| 5,000+ | ~10⁻¹¹ | Pure noise |
| 34,319 | ~10⁻⁷⁵ | Pure noise |

This framework is not a disqualifier on its own — some teams achieve signal through
high shot counts, careful post-processing, or genuinely shallow circuits — but it
is the first question to ask when evaluating a claimed hardware result.

---

## Detailed Reviews

---

### SteveTipp / Steve Tippeconnic
**Repository:** https://github.com/SteveTipp/Qwork.github.io
**arXiv:** [2507.10592](https://arxiv.org/abs/2507.10592) — *"Breaking a 5-Bit Elliptic Curve Key using a 133-Qubit Quantum Computer"*

As of the competition deadline, SteveTipp is **the most publicly prominent submission**:
arXiv-published (Jul 2025, 32 pages), highlighted by Project Eleven as "first-ever
quantum attack on an ECC key," and the most technically documented submission found.

**Circuit (5-bit, Experiment 73):**

| Parameter | Value |
|-----------|-------|
| Hardware | IBM ibm_torino (133-qubit Heron r1) |
| Qubits | 15 (10 logical + 5 ancilla) |
| CZ gates (transpiled) | **34,319** |
| Circuit depth | **67,428** |
| Shots | 16,384 |

**Claimed result:** "k=7 found in top 100 invertible (a,b) results."

**Statistical analysis** (from our internal review of their raw data,
`competition/stevetipp/analysis.md`):

- k=7 received 54/16,384 shots — ranked ~4th, not 1st (k=8 had 63 shots, k=0 had 54)
- With best post-processing (toroidal smoothing + weighted exact-line scoring): k=7 reaches **rank 3**, not rank 1
- Bootstrap robustness (500 replicates): **k=7 wins rank-1 in 0/500 replicates (0%)**; k=0 wins 500/500
- Their own analysis file (`FIVE_BIT_INTERFERENCE_ANALYSIS_NOTE.md`) records: `true_k_rank_1_rate = 0.0`
- 6-bit QDay submission: after 10+ post-processing stages, correct key reaches rank 3 only; bootstrap rank-1 rate remains 0%

**Circuit fidelity:** `0.995^34,319 ≈ 1.4 × 10⁻⁷⁵`. The output is noise. The "diagonal
ridge in the 32×32 QFT outcome space" described in the abstract is consistent with
readout bias and crosstalk artifacts in a pure-noise regime.

**Assessment:** The result is technically true as stated — k=7 does appear in the top
100. But "top 100 out of 32 possible values" is a weak claim, and the 0% bootstrap
rank-1 rate indicates the result is not reproducible. The 10+ stage post-processing
pipeline tuned against the known answer is the actual recovery mechanism, not the
quantum circuit.

Project Eleven's characterization as "first-ever quantum attack on an ECC key" reflects
the visibility of the arXiv publication, not the statistical strength of the result.

---

### SilkForgeAi / VexaAI
**Repository:** https://github.com/SilkForgeAi/QDayPrizeSubmission
**Contact:** Aaron@vexaai.app

**Results:**

| Key size | Qubits | Transpiled gates | Depth | Shots | Success rate | IBM Job ID |
|----------|--------|-----------------|-------|-------|-------------|------------|
| 4-bit (n=7) | 15 | ~280 | ~4,000 | 5,000 | 1.92% | d53hle9smlfc739eskn0 |
| 6-bit (n=31) | 19 | ~10,000 | ~65,000 | 20,000 | 2.915% | d53i7nfp3tbc73amgl2g |
| 7-bit (n=79) | 23 | ~423,000 | ~241,000 | 50,000 | 1.13% | d53ijmgnsj9s73b0vf60 |

IBM Job IDs are publicly verifiable via IBM Quantum Cloud.

**"Noise-assisted quantum computing":** They report that hardware outperforms simulator
by up to 56.5× at 7-bit, attributing this to constructive interference from IBM Torino's
specific noise profile. This is an unusual claim worth careful scrutiny: at 423,000
transpiled gates, any genuine fidelity estimate is astronomically close to zero. A 1.13%
success rate at n=79 is also close to random (1/79 ≈ 1.27%). The 6-bit result
(~65,000 gate depth) faces the same problem.

Their **4-bit result** is more credible — ~280 gates at depth ~4,000 puts it near the
noise floor but potentially within range. The published job IDs confirm the jobs ran;
they do not by themselves confirm that the quantum circuit contributed to the recovery
as opposed to post-processing.

**Assessment:** Most verifiable submission in the competition due to published job IDs.
The 4-bit claim is plausible. The 6-bit and 7-bit claims are difficult to reconcile
with the fidelity math, and the noise-assisted narrative requires independent validation.

---

### Matrix CR / Pablo Ramirez
**Repository:** https://github.com/pabl0ramirez/qday-prize-matrixcr
**Contact:** pablo@matrixcr.ai

**Approach:** Full quantum oracle — precomputes all N² EC point combinations as a
multi-controlled-X lookup table on IBM ibm_fez (Heron r2, 156 qubits).

**Results:**

| Key size | Qubits | Circuit depth | Shots | Signal | Success rate |
|----------|--------|---------------|-------|--------|-------------|
| 4-bit (n=7) | 9 | 150 | 2,048 | 265/2,048 | **12.9%** |
| 6-bit (n=31) | 15 | 4,188 | 4,096 | 127/4,096 | **3.1%** |

Circuit depth 150 at 4-bit implies very few 2Q gates — consistent with the 12.9%
signal. Depth 4,188 at 6-bit with ~25% 2Q gates implies ~1,000 CZ gates, giving
fidelity ~0.5–5% — consistent with their reported 3.1%. The results are internally
coherent with the fidelity framework.

Every recovered key is verified classically via `k·G = Q`. They explicitly acknowledge
that the O(N²) oracle construction limits scalability to roughly 6-bit on current hardware.

**Assessment:** Technically honest, well-documented, and the fidelity math supports
the claimed signal. The 6-bit result is the most credible large-key claim in the
competition by this metric.

---

### Justin Hughes Firebringer
**Repository:** https://github.com/JustinHughesFirebringer/QDay

**Claimed:** 12-bit break (k=1384, p=2089) on IBM ibm_fez. 2D Shor variant with
Möbius Scaffold Stabilization, 156 qubits, transpiled depth 31,667.

Their own documentation is candid: *"results NISQ-noise dominated"*, *"candidate
distributions typically flat"*, *"success relies on candidate verification rather
than dominant QPE peak."* The correct key is not the top result — it is found by
classical verification over a large candidate pool. A 31,667-depth circuit on IBM
hardware has near-zero fidelity.

**Assessment:** Honest self-assessment. The quantum circuit does not produce a
meaningful signal at this depth; the claimed "break" is classical candidate search
seeded by a noise distribution.

---

### adityayadav76 / Automatski
**Repository:** https://github.com/adityayadav76/qday_prize_submission

7–8 bit results on Automatski's proprietary hardware (claimed: 70 logical qubits,
99.999% 2Q fidelity, 43-minute coherence). These specifications — if accurate —
would represent a 10–100× improvement over any publicly benchmarked quantum system.
There is no peer-reviewed publication or independent benchmark for the Automatski
platform. Reproduction requires contacting the author for hardware access.

**Assessment:** Reproducibility concern as the primary issue. The circuit code is
competent; the hardware claims are unverifiable.

---

### hk-quantum
**Repository:** https://github.com/hk-quantum/qday-prize

Custom `SparseStatevectorSimulator` produces correct results up to 12-bit. IBM ibm_fez
hardware results at 5-bit: author states output was *"essentially random and did not
reach expected accuracy."* This is an honest assessment worth noting — the simulator
work is credible, but does not satisfy the competition's hardware requirement.

---

### Stubs (Davevinci7 ×2, skylarthehoster)

No code. Not substantive submissions.

---

## Our Submission in Context

| Dimension | Our submission | Matrix CR (6-bit) | SteveTipp (5-bit, arXiv) | SilkForgeAi (7-bit) |
|-----------|---------------|-------------------|--------------------------|---------------------|
| Key size on hardware | 4-bit | 6-bit | 5-bit | 7-bit (claimed) |
| 2Q gates | 716 CX | ~1,000 CZ est. | 34,319 CZ | ~100k+ CZ est. |
| Circuit fidelity | ~2.8% | ~1–5% | ~10⁻⁷⁵ | ~0 |
| Key recovery | Direct top-1 mode | 3.1% direct signal | Rank 3 in 500 bootstraps (0% rank-1) | Consistent with random (1/n) |
| Post-processing | `mode(-x2_r · x1_r⁻¹ mod n)` | Classical `k·G = Q` check | 10+ engineered stages | Candidate verification |
| Scalable oracle | ✅ Method B (EC arithmetic, d never used) | ❌ O(N²) lookup | ❌ Scalar encoding | ❌ Scalar encoding |

Our 4-bit hardware result is smaller in key size than several competitors, but sits
clearly above the noise floor and requires no engineered post-processing. The scalable
Method B circuit (105,554 CX) is the only genuine EC arithmetic oracle in the competition
where `d` is never computed — the algorithm that would actually work at cryptographic
scale with sufficient hardware.

**The strongest technically credible results in the competition, in order:**
Matrix CR's 6-bit (depth 4,188, 3.1% signal) and our 4-bit (716 CX, 2.8% fidelity,
direct recovery) are the two results most consistent with the fidelity framework.
All larger claimed key sizes require either unverifiable hardware, elaborate
post-processing pipelines, or circuits with near-zero fidelity.
