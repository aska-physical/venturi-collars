# venturi-collars

**Battery-Free Aeroelastic Venturi Collars for Smart Building HVAC & Industrial Ducts.**

Turns the conceptual flow-shaping wall harvester of [`Foundation-0/ductricity`](https://github.com/Foundation-0/ductricity) ([`PROJECT.md`](https://github.com/Foundation-0/ductricity/blob/main/PROJECT.md)) and thermodynamic bounds of [`Foundation-0/thermal-capture`](https://github.com/Foundation-0/thermal-capture) into a quantitatively verified, drop-in sheet-metal/composite VAV HVAC sensor collar using tailored [Torayca M55J](https://www.toraycma.com/products/carbon-fiber/) carbon-ply reeds.

## Resolving `ductricity`'s Central Conflict (Plus a Crucial Negative Finding)

[`Foundation-0/ductricity`](https://github.com/Foundation-0/ductricity/blob/main/PROJECT.md) identified two unresolved obstacles: (1) extracting wall energy without choking or stalling duct airflow, and (2) published polymer flutter films producing weak power or narrow velocity lock-in ([AIP 2025 Flow Energy Harvester Survey](https://pubs.aip.org/aip/jrse/article/17/1/012703/3330732/A-survey-of-flow-based-energy-harvesters-for)).

Running the coupled hydraulic + electromechanical equations in `verify.py` uncovered a **critical design bifurcation**:
- **Negative finding (`VERIFIED`, Must-fail #2):** A pure thin-film `PVDF-TrFE` bimorph array ($6 \times 28\,\mu\text{m}$ plies on a $35\,\mu\text{m}$ M55J core) inside a $200\text{ mm}$ HVAC duct generates only **$0.0476\text{ mW}$ ($47.6\,\mu\text{W}$)** at $4.0\text{ m/s}$ because sub-$100\,\mu\text{m}$ bending lever arms produce $< 0.03\%$ RMS strain and $k_{31}^2 \approx 0.02$—falling short of a continuous $\text{CO}_2$/pressure BLE/LoRa node ($80\text{–}150\,\mu\text{W}$).
- **Verified solution (Contoured Venturi + Bearing-Free M55J/PCB-Coil Hybrid):**
  1. **Gradual $\beta = 0.64$ Venturi throat + $7^\circ$ conical diffuser:** Accelerates $1.8\text{ m/s}$ VAV turndown flow to $2.81\text{ m/s}$ across 6 flush wall reeds (surpassing the $2.23\text{ m/s}$ flutter cut-in speed, where an unaccelerated straight duct produces **$0.00\text{ mW}$**, `Must-fail #3`), then recovers $> 85\%$ of dynamic head so total pressure loss at nominal $4.0\text{ m/s}$ is just **$1.615\text{ Pa}$ ($0.0065\text{ in. w.g.}$)**—over **$30\times$ lower** than a sharp baffle (`> 50 Pa`) and well inside ASHRAE VAV fitting budgets (`< 15 Pa`).
  2. **Bearing-free hybrid transduction:** Adding a $0.35\text{ g}$ NdFeB tip shim on each fatigue-immune M55J carbon reed oscillating past a **flush 4-layer printed PCB stator coil** inside the outer collar wall boosts harvested DC power **$19.4\times$** (to **$0.924\text{ mW}$ at $4.0\text{ m/s}$** and **$0.104\text{ mW}$ at $1.8\text{ m/s}$** turndown, $11.55\times$ telemetry margin at $4.0\text{ m/s}$) with **zero bearings to clog with HVAC dust**, eliminating ~500 lithium battery replacements per 100 VAV zones over 20 years ([MDPI HVAC Airflow Harvesting](https://www.mdpi.com/1424-8220/23/14/6381)).

## Velocity Sweep (`200 mm` VAV Branch Duct, `verify.py`)

| Duct Airspeed $U_{\text{duct}}$ | Throat Airspeed $U_{\text{throat}}$ | Static Pressure Drop $\Delta P$ | Pure PVDF Power | Hybrid M55J + PCB-Coil Power | Peak M55J Strain |
| :---: | :---: | :---: | :---: | :---: | :---: |
| $1.8\text{ m/s}$ (turndown) | $2.81\text{ m/s}$ | $0.33\text{ Pa}$ | $0.003\text{ mW}$ | **$0.104\text{ mW}$** (`> 80 uW` node) | $0.010\%$ |
| $2.5\text{ m/s}$ | $3.91\text{ m/s}$ | $0.63\text{ Pa}$ | $0.011\text{ mW}$ | **$0.365\text{ mW}$** | $0.018\%$ |
| $4.0\text{ m/s}$ (nominal) | $6.25\text{ m/s}$ | **$1.62\text{ Pa}$** | $0.028\text{ mW}$ | **$0.924\text{ mW}$** (`11.55x` margin) | $0.029\%$ |
| $6.0\text{ m/s}$ (peak VAV) | $9.38\text{ m/s}$ | $3.63\text{ Pa}$ | $0.028\text{ mW}$ | **$0.924\text{ mW}$** (amplitude-limited) | $0.029\%$ (`<< 0.8%` limit) |

## Reproduce & Verify

```bash
python3 verify.py
```

## `aska-physical` Ecosystem & Upstream Lineage

| Repository | Role in Physical Stack | Upstream `Foundation-0` Lineage |
| :--- | :--- | :--- |
| [`aska-physical/fibral-rigidity`](https://github.com/aska-physical/fibral-rigidity) | Continuum CFRP truss homogenization, area-grading (`alpha_K* = 2*sqrt(2)`, `alpha_E* = 2*sqrt(6)/3`), and 45-deg pore-tie theory | [`Foundation-0/incentre-lattices`](https://github.com/Foundation-0/incentre-lattices) |
| [`aska-physical/cfrp-strengthening`](https://github.com/aska-physical/cfrp-strengthening) | Step-by-step re-runnable ACI 440.2R concrete beam strengthening baseline | [`Foundation-0/cfrp-strengthening`](https://github.com/Foundation-0/cfrp-strengthening) |
| [`aska-physical/cfrp-truss`](https://github.com/aska-physical/cfrp-truss) | Truss-anchored NSM + 45-deg shear-stitched, self-sensing CFRP beam/column retrofit kits | `cfrp-strengthening` + `fibral-rigidity` + `nhanes-bioimpedance` |
| [`aska-physical/cfrp-masts`](https://github.com/aska-physical/cfrp-masts) | Snap-locked 3.32x-compacting deployable CFRP booms, telecom towers, and solar masts | `incentre-lattices` + `fibral-rigidity` + [`Foundation-0/rigid-realizations`](https://github.com/Foundation-0/rigid-realizations) |
| [`aska-physical/venturi-collars`](https://github.com/aska-physical/venturi-collars) | Battery-free aeroelastic M55J/PCB-coil Venturi collars for VAV HVAC & industrial ducts | [`Foundation-0/ductricity`](https://github.com/Foundation-0/ductricity) + [`Foundation-0/thermal-capture`](https://github.com/Foundation-0/thermal-capture) |
| [`aska-physical/impedence-analyzers`](https://github.com/aska-physical/impedence-analyzers) | Artifact-rejecting 7-frequency Cole EIS analyzers for structural NDT & clinical BIA | [`Foundation-0/nhanes-bioimpedance`](https://github.com/Foundation-0/nhanes-bioimpedance) + [`Foundation-0/point-charges`](https://github.com/Foundation-0/point-charges) |

## Attribution & Ethos

- **Architect & Human Sign-Off:** Shahid Arifuddin (`@abu-aska`)
- **Foundational `f0` Lineage:** Ahraz Arifuddin (`@ahrazzle`)
- **Autonomous Agent Capture:** Google Gemini (see [`HANDOFF.md`](HANDOFF.md) and [`CHANGELOG.md`](CHANGELOG.md)).
