# Changelog

## [1.1.0] - 2026-11-25
### Fixed
- **Dimensionless supercritical Hopf amplitude (`supercritical_vel_factor`):** Removed the unexplained dimensional `+ 6.0` (`m^2/s^2`) constant from the flutter velocity denominator (replacing it with explicit optional `U_sat_m_s = 0.0` default). At `1.8 m/s` turndown, model output moves from `1.341 mm` / `0.1040 mW` to `1.991 mm` / `0.2291 mW` (conditioned on the uncalibrated `0.0026 m` amplitude prefactor in `verify.py:249`, confirming legacy `0.4539x` power distortion); `4.0` and `6.0 m/s` remain mechanically amplitude-limited at `4.0 mm` (`0.9244 mW`, `11.55x` margin).
- **Continuous conical diffuser stall loss (`compute_venturi_loss_coeff`):** Replaced the flat `<= 8°` loss constant and discontinuous `8.01°` Borda-Carnot cliff with continuous conical Darcy wall friction, Gibson's conical expansion factor layered with a conservative in-repo area-ratio stall-intensification heuristic (`two_theta_stall = 16/(AR-1)^0.35`, not a cited literature correlation), and an in-repo sharp-edged orifice/baffle vena-contracta transition heuristic (`C_c: 1.0 -> 0.61` over `15..45°`). Produces a friction-vs-stall minimum near `4°` (`K = 0.1457`), design `7°` (`K = 0.1608`, `dP = 2.212 Pa < 6.0 Pa` at `4.0 m/s`), transitory stall at `15°` (`K = 0.3188`, `dP = 3.734 Pa`), full stall at `25°` (`K = 0.6998`), and sharp-edged orifice-plate/baffle comparison at `45°, beta = 0.50` (`52.662 Pa`).
- **Incompressible Mach validity gate & overflow hardening:** Added speed of sound `a_sound = 343.232 m/s` (`20 °C`), fail-closed `Ma_throat <= 0.30` guard rejecting choked/compressible contractions (e.g., `beta = 0.05` at `6.0 m/s`, `Ma = 0.350 > 0.30`), and `strict_finite_pow` guards converting extreme-input `OverflowError`s into `CheckFailure`.
- Expanded `must_fail_controls` from `5` to `8` (with Control #6 verifying the default `evaluate_venturi_collar` call directly against `U_sat_m_s = 0.0` vs `sqrt(6.0)`), added zero-bare-assert R5 regression suite (`tests/test_physical_hardening.py`), synchronized `HANDOFF.md` (`0.0118 mW` pure PVDF / `0.0069 mW` hybrid piezo share at `1.8 m/s`), and regenerated `results/certificate.json` (`v1.1.0`).

## [1.0.0] - 2026-11-22
### Changed
- Hardened `verify.py` with `CheckFailure` guards (`-O`-safe, zero bare `assert`s), NaN-safe finite clamps (`strict_finite_min`/`strict_finite_max`), and canonical-byte symlink-safe `results/certificate.json` verification (`certificate_version: "1.0.0"`), plus regression suites (`tests/test_verify_O_safety.py`, `tests/test_verify_nan_zoneb.py`).

## [0.1.0] - 2026-11-14
### Added
- Initialized `aska-physical/venturi-collars` baseline (`README.md`, `HANDOFF.md`, `CHANGELOG.md`, `verify.py`, `results/certificate.json`).
- Quantified and recorded negative finding on pure thin-film PVDF-TrFE VAV flutter (`0.0476 mW` at `4.0 m/s`), and verified bearing-free M55J CFRP + flush PCB-coil hybrid Venturi collar (`0.104–0.924 mW` across `1.8–6.0 m/s` at `0.33–3.63 Pa` static pressure loss) with 5 must-fail controls.
