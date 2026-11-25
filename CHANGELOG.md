# Changelog

## [1.1.0] - 2026-11-25
### Fixed
- **Dimensionless supercritical Hopf amplitude (`supercritical_vel_factor`):** Removed the unexplained dimensional `+ 6.0` (`m^2/s^2`) constant from the flutter velocity denominator (replacing it with explicit optional `U_sat_m_s = 0.0` default). At `1.8 m/s` turndown, tip amplitude restores from `1.341 mm` to `1.991 mm` and harvested power from `0.1040 mW` to `0.2291 mW` (confirming legacy `0.4539x` power distortion); `4.0` and `6.0 m/s` remain mechanically amplitude-limited at `4.0 mm` (`0.9244 mW`, `11.55x` margin).
- **Continuous conical diffuser stall loss (`compute_venturi_loss_coeff`):** Replaced the flat `<= 8°` loss constant and discontinuous `8.01°` Borda-Carnot cliff with a continuous Gibson/Idelchik conical diffuser Darcy-friction + Kline-Reneau `(2*theta, AR=1/beta)` stall model and smooth sharp-baffle vena-contracta onset (`C_c: 1.0 -> 0.61` over `15..45°`). Produces physical friction-vs-stall minimum near `4°` (`K = 0.1457`), design `7°` (`K = 0.1608`, `dP = 2.212 Pa < 6.0 Pa` at `4.0 m/s`), transitory stall at `15°` (`K = 0.3188`, `dP = 3.734 Pa`), full stall at `25°` (`K = 0.6998`), and abrupt `45°` baffle (`52.662 Pa` at `beta = 0.50`).
- **Incompressible Mach validity gate:** Added speed of sound `a_sound = 343.232 m/s` (`20 °C`) and fail-closed `Ma_throat <= 0.30` guard rejecting choked/compressible contractions (e.g., `beta = 0.05` at `6.0 m/s`, `Ma = 0.350 > 0.30`).
- Expanded `must_fail_controls` from `5` to `8`, added zero-bare-assert R5 regression suite (`tests/test_physical_hardening.py`), and regenerated `results/certificate.json` (`v1.1.0`).

## [0.1.0] - 2026-11-14
### Added
- Initialized `aska-physical/venturi-collars` baseline (`README.md`, `HANDOFF.md`, `CHANGELOG.md`, `verify.py`, `results/certificate.json`).
- Quantified and recorded negative finding on pure thin-film PVDF-TrFE VAV flutter (`0.0476 mW` at `4.0 m/s`), and verified bearing-free M55J CFRP + flush PCB-coil hybrid Venturi collar (`0.104–0.924 mW` across `1.8–6.0 m/s` at `0.33–3.63 Pa` static pressure loss) with 5 must-fail controls.
