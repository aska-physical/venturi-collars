# Cascaded Choke Contraction & Cycle-Space Passive Ventilation Audit (`VENTURI-BIO-OP23`)

- **Target Repository:** `aska-physical/venturi-collars` (add-only study off `origin/main @ d53f85a35d17a7bd`; zero edits to `verify.py` or `results/certificate.json`).
- **Governance & Claim Scope (`aska-physical/dock#8`):** All results here are **`model` / `checker`** mathematical proofs in pure Python 3 standard-library exact arithmetic (`int`, `fractions.Fraction`, `math.comb`). Zero IEEE-754 floats on trust paths, zero bare `assert`s, zero external dependencies, zero bench claims.
- **Anchored Source Lines (`venturi-collars/verify.py @ d53f85a3`):**
  - `verify.py:17-41` — isolated 1D duct & `K_venturi` gradual (`7 deg`) vs. abrupt (`45 deg`) diffuser pressure loss.
  - `verify.py:68-69` — hard reed tip-amplitude clamp `min(0.0040, ...)`.
  - `verify.py:109-125` — isolated 1D duct velocity sweep & abrupt `45 deg` baffle control.

---

## Certified Exact-$\mathbb{Z}/\mathbb{Q}$ Pillars

1. **Pillar 1 — Cascaded Load Splitting, Multi-Stage Attenuation & Rational Negative-Feedback Choke (Operator 2):**
   - **Exact $K$-stage hydrostatic splitting ($H=8$):** Equal-stage cascades $K \in \{1, 2, 4, 8\}$ achieve exact overturning-moment reduction $M_{\mathrm{mono}}/M_{\mathrm{stage}} = K^3 \in \{1, 8, 64, 512\}$ and total-thrust reduction $F_{\mathrm{mono}}/F_{\mathrm{tot}} = K \in \{1, 2, 4, 8\}$ with `jensen_excess = 0/1`, cross-checked against exact pairwise identity $\frac{1}{K}\sum_{i<j}(h_i-h_j)^2$. Unequal partition `(4, 4/3, 4/3, 4/3)` carries exact `jensen_excess = 16/3`, dropping peak-moment reduction `64 -> 8` and thrust reduction `4 -> 3`.
   - **Exact discrete cascade convolution vs. negative-binomial closed form ($\alpha = 1/2, 16$ steps):** Exact match across all steps with monotone peak attenuation `1/2 (t=0) > 1/4 (t=0) > 5/32 (t=2) > 429/4096 (t=6)`. Honest fixed-residence-time control ($\tau = 7, \alpha_K = K/(K+7)$) explicitly discloses non-monotonicity (`1/8 > 5488/59049 < 1129026575925248/9730975341796875`) when subdividing fixed storage without adding volume.
   - **Exact rational choke feedback ($g_0 = 1, h = 1, \alpha = \beta = 1/4, T = 5$):** Replaces the hard clamp in `verify.py:68-69` with contractive $g_{t+1} = g_t/(1+\alpha q_t^2)$, proving strict contraction to `529177918180/1014556267661` ($\approx 0.5216$) satisfying the telescoping Lyapunov bound $g_t^{-2} > g_0^{-2} + 2 t \alpha h^2$ at every step, vs. positive-feedback runaway $g_{t+1} = g_t(1+\beta q_t^2)$ exceeding $521\times$ the contractive value at $T=5$.

2. **Pillar 2 — Cycle-Space Passive Ventilation & Blockage Survivability (Operator 3):**
   - **Dual exact-$\mathbb{Q}$ Kirchhoff solver** (nodal weighted Laplacian $B G B^\top \phi = B G \eta$ cross-checked identically against independent fundamental cycle-basis solve $(C G^{-1} C^\top) i_{\mathrm{loop}} = C\eta$, verifying $B q = 0$ and $\eta^\top q = q^\top G^{-1} q$) on 8-junction collar manifolds:
     - `tree_duct` (`|E|=7, beta_1=0`): `convective_power = 0/1` (zero flow regardless of driving head).
     - `ring_duct` with elevation coboundary $\eta = B^\top z$ (`|E|=8, beta_1=1`): `convective_power = 0/1` (proves $\beta_1 \ge 1$ alone is insufficient; requires $[\eta] \ne 0 \in H^1(G;\mathbb{Q})$).
     - `ring_duct` with non-coboundary stack head (`|E|=8, beta_1=1`): `convective_power = 1/2` and exact diurnal sign reversal $q(-\eta) = -q(\eta)$.
     - `redundant_collar_3loop` (`|E|=10, beta_1=3`): `convective_power = 15/14`.
   - **Exhaustive 1-edge and 2-edge duct-blockage survival fractions:**
     - `tree_duct` (`|E|=7`): 1-edge `0/1`, 2-edge `0/1`.
     - `ring_duct` (`|E|=8`): 1-edge **`1/1`**, 2-edge `0/1`.
     - `redundant_collar_3loop` (`|E|=10`): 1-edge **`1/1`**, 2-edge **`38/45`** (disconnect `7/45`).
     - `cube_collar_5loop` (`|E|=12`): 1-edge **`1/1`**, 2-edge **`1/1`**.

3. **Pillar 3 — `dock#8` Receiving-Side Pass/Fail Collar Gate:**
   - **PASS** on balanced 4-stage contractive 3-loop collar (`failed_reasons = []`).
   - **FAIL** on 5 distinct negative controls: `CHOKE_NOT_CONTRACTIVE` (runaway feedback), `NONZERO_JENSEN_EXCESS` (unbalanced stages), `BETTI1_ZERO_NO_CYCLE` + `ZERO_PASSIVE_CIRCULATION` + `SINGLE_EDGE_BLOCKAGE_VULNERABLE` (tree duct), `ZERO_PASSIVE_CIRCULATION` (coboundary-blocked loop), and `SINGLE_EDGE_BLOCKAGE_VULNERABLE` alone (looped bridge manifold).

---

## Reproduce & Verify

```bash
for flags in "-I -B" "-I -O -B" "-I -B -W error" "-I -O -B -W error"; do
  python3 $flags cascaded_cycle_ventilation_audit.py --check cascaded_cycle_ventilation_certificate.json
  python3 $flags test_cascaded_cycle_ventilation_r5.py
done
PYTHONHASHSEED=42 python3 -I -B cascaded_cycle_ventilation_audit.py --standalone --json | sha256sum
```

- **Pinned Certificate Digests (`cascaded_cycle_ventilation_certificate.json`):**
  - `payload_sha256`: `4d84ea71121f6db6af4bbbd7078954955322acc8aa112ab0ecd788cdbc254492`
  - `certificate_sha256`: `b357c1e326459d82ab8805d1853d5af885c8b53d73409d2a6b6d4677ac751f02`
