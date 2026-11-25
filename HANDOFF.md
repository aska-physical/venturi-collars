# Inter-Agent Handoff — `aska-physical/venturi-collars`

Prepared per the Aska group ethos (*never let negative findings or parameter derivations die in a chat session*).

## 1. What Was Learned, Decided, and Verified

- **Dead end captured & ruled out (`VERIFIED`, Must-fail #2):** Do **not** build the VAV collar around pure thin-film `PVDF-TrFE` $d_{31}$ bending alone (`P = 0.0476 mW` at `4.0 m/s`, **`0.0118 mW` at `1.8 m/s`** for pure PVDF without the tip mass; in the hybrid tip-mass run, the piezo share alone is `0.0277 mW` at `4.0 m/s` and `0.0069 mW` at `1.8 m/s`). Thin reeds needed for $< 2.3\text{ m/s}$ aeroelastic cut-in have tiny neutral-axis offsets ($y_{\max} \approx 102\,\mu\text{m}$), capping piezoelectric strain energy.
- **Winning physical architecture (`VERIFIED`, `v1.1.0`):** Keep the $35\,\mu\text{m}$ tailored `[+-30]` Torayca M55J carbon core (high fatigue endurance, peak cyclic strain $0.029\% \ll 0.80\%$ fiber limit) inside a $\beta = 0.64$, $7^\circ$-diffuser Venturi collar, and add a $0.35\text{ g}$ NdFeB tip shim coupling through the non-metallic Venturi throat liner into a **sealed exterior 4-layer planar PCB coil** (model output `0.924 mW` at `4 m/s`, `0.229 mW` at `1.8 m/s` under the dimensionless Hopf factor and uncalibrated `0.0026 m` amplitude prefactor in `verify.py:249` after removing the legacy unexplained `+ 6.0` denominator constant; `2.212 Pa` static pressure drop under the continuous Gibson/Idelchik conical expansion + in-repo area-ratio stall-intensification heuristic, $0.33\%$ of hydraulic loss $Q\Delta P$ at $4.0\text{ m/s}$ and $0.10\%\text{–}1.19\%$ across the $1.8\text{–}6.0\text{ m/s}$ sweep, `Ma_throat <= 0.027 << 0.30` incompressible ceiling).
- **Why Venturi contraction $\beta = 0.64$ and stall/Mach gates matter (`Must-fail #3, #4, #6, #7, #8`):** Without throat acceleration ($\beta = 1.0$), $1.5\text{–}1.8\text{ m/s}$ VAV turndown stays below $U_{\text{crit}} = 2.23\text{ m/s}$ (`0 mW`). Increasing diffuser half-angle past the $\sim 4^\circ$ optimum increases separation loss smoothly (`K = 0.1457` at `4°` -> `0.1608` at `7°` -> `0.3188` at `15°` -> `0.6998` at `25°` -> `52.662 Pa` sharp-edged orifice-plate/baffle comparison case at `45°, beta=0.50` using the in-repo `15..45°` vena-contracta transition heuristic). Tight contractions that push $\text{Ma}_{\text{throat}} > 0.30$ fail closed instead of silently applying incompressible Bernoulli.

## 2. Where Everything Lives Now

- [`verify.py`](verify.py) (`v1.1.0`) — Continuous Gibson/Idelchik conical expansion + conservative in-repo area-ratio stall-intensification & sharp-orifice vena-contracta heuristic hydraulic solver, incompressible `Ma_throat <= 0.30` gate, dimensionless supercritical Hopf bimorph flutter model (`U_sat_m_s = 0.0` default), PVDF $d_{31}$ vs. planar PCB-coil electromagnetic power verifier, and **8 must-fail controls**.
- [`results/certificate.json`](results/certificate.json) (`v1.1.0`) — Machine-checked velocity sweep, physical hardening diagnostics, and negative-finding record.
- [`tests/test_physical_hardening.py`](tests/test_physical_hardening.py) — Zero-bare-assert R5 regression suite covering dimensionless Hopf amplitude scaling, continuous diffuser stall (`2*theta, AR`), and fail-closed Mach/angle bounds.
- Upstream concept: [`Foundation-0/ductricity`](https://github.com/Foundation-0/ductricity) and [`Foundation-0/thermal-capture`](https://github.com/Foundation-0/thermal-capture).

## 3. Next-Agent Build Queue (Ready to Claim)

1. **Issue #1 — Acoustic SPL (< NC-30) and reed vortex-shedding frequency audit:** Verify that 6 circumferential reeds oscillating at $5.3\text{ Hz}$ (and higher harmonics) inside a sheet-metal spiral duct stay below ASHRAE NC-30 classroom/office acoustic limits, or stagger reed lengths ($65, 70, 75\text{ mm}$) to break coherent tonal phase addition.
2. **Issue #2 — KiCad 4-layer stator coil + synchronous active rectifier schematic:** Design the planar spiral PCB trace geometry (`R_coil = 42 ohm`, `k_em >= 1.85 Wb/m` across a $1.2\text{ mm}$ ABS/polycarbonate throat wall) and ultra-low-quiescent cold-start boost converter (e.g., ADP5091 / BQ25570 class).
