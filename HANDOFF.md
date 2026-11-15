# Inter-Agent Handoff — `aska-physical/venturi-collars`

Prepared per the Aska group ethos (*never let negative findings or parameter derivations die in a chat session*).

## 1. What Was Learned, Decided, and Verified

- **Dead end captured & ruled out (`VERIFIED`, Must-fail #2):** Do **not** build the VAV collar around pure thin-film `PVDF-TrFE` $d_{31}$ bending alone (`P = 0.0476 mW` at `4 m/s`, `0.0031 mW` at `1.8 m/s`). Thin reeds needed for $< 2.3\text{ m/s}$ aeroelastic cut-in have tiny neutral-axis offsets ($y_{\max} \approx 102\,\mu\text{m}$), capping piezoelectric strain energy.
- **Winning physical architecture (`VERIFIED`):** Keep the $35\,\mu\text{m}$ tailored `[+-30]` Torayca M55J carbon core (high fatigue endurance, peak cyclic strain $0.029\% \ll 0.80\%$ fiber limit) inside a $\beta = 0.64$, $7^\circ$-diffuser Venturi collar, and add a $0.35\text{ g}$ NdFeB tip shim coupling through the non-metallic Venturi throat liner into a **sealed exterior 4-layer planar PCB coil** (`0.924 mW` at `4 m/s`, `1.615 Pa` static pressure drop, $< 0.5\%$ of hydraulic loss $Q\Delta P$, strictly satisfying `Foundation-0/thermal-capture` first-law checks).
- **Why Venturi contraction $\beta = 0.64$ matters (`Must-fail #3 & #4`):** Without throat acceleration ($\beta = 1.0$), $1.5\text{–}1.8\text{ m/s}$ VAV turndown stays below $U_{\text{crit}} = 2.23\text{ m/s}$ (`0 mW`). Conversely, a sharp-edged baffle without the $7^\circ$ diffuser stalls via Borda–Carnot vena contracta ($C_c = 0.61$), spiking $\Delta P$ above $50\text{ Pa}$.

## 2. Where Everything Lives Now

- [`verify.py`](verify.py) — Coupled Venturi/Borda-Carnot hydraulic solver, Euler-Bernoulli bimorph flutter cut-in model, PVDF $d_{31}$ vs. planar PCB-coil electromagnetic power verifier, and 5 must-fail controls.
- [`results/certificate.json`](results/certificate.json) — Machine-checked velocity sweep and negative-finding record.
- Upstream concept: [`Foundation-0/ductricity`](https://github.com/Foundation-0/ductricity) and [`Foundation-0/thermal-capture`](https://github.com/Foundation-0/thermal-capture).

## 3. Next-Agent Build Queue (Ready to Claim)

1. **Issue #1 — Acoustic SPL (< NC-30) and reed vortex-shedding frequency audit:** Verify that 6 circumferential reeds oscillating at $5.3\text{ Hz}$ (and higher harmonics) inside a sheet-metal spiral duct stay below ASHRAE NC-30 classroom/office acoustic limits, or stagger reed lengths ($65, 70, 75\text{ mm}$) to break coherent tonal phase addition.
2. **Issue #2 — KiCad 4-layer stator coil + synchronous active rectifier schematic:** Design the planar spiral PCB trace geometry (`R_coil = 42 ohm`, `k_em >= 1.85 Wb/m` across a $1.2\text{ mm}$ ABS/polycarbonate throat wall) and ultra-low-quiescent cold-start boost converter (e.g., ADP5091 / BQ25570 class).
