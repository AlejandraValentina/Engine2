# PyWaveDyn v2.0 — Technical Specs (Advanced Coupled Physics)

## 0) Scope & Compatibility
- **Parallel core:** v2.0 lives under `core/advanced/` and does **not** replace the v1.0 core.
- **Product naming:** v1.0 remains **Quick Dyno**. v2.0 is the **Advanced Physics Core**.
- **Backward compatibility:** presets JSON must remain compatible via defaults and tolerant parsing.

### 0.1 Status & Evidence
- Implementation status and evidence live in `FEATURES.md`.
- Canonical validation commands live in `VALIDATION_GUIDE.md`.

### 0.2 Phase Naming
- **Phase 1:** baseline contract (static reservoir assumptions for totals when configured).
- **Phase 2:** totals-aware coupling (stagnation-based direction, ghost inversion, K-loss rules).

## 1) Architecture
**Modules and responsibilities (Phase 1):**
- **CylinderControlVolume**
  - Open-system thermodynamics.
  - Tracks mass and energy with flow enthalpy and variable mass (dm/dt ≠ 0).
- **WaveNetwork1D**
  - Unsteady 1D compressible flow solver in networked pipes.
- **CouplingInterface**
  - Valve/nozzle boundary contract. Applies **fluxes**, not pressure forcing.
- **Orchestrator**
  - Adaptive time loop, convergence detection, synchronization across 0D/1D.

### 1.1 Convergence Monitor Output
The orchestrator exports per-cycle convergence metrics as a JSON-serializable list:
- `k`: cycle iteration index (0-based).
- `err_trapped_mass`: relative change in trapped mass vs previous cycle.
- `err_imep`: relative change in IMEP vs previous cycle.
- `err_periodicity_1d`: L2 norm of 1D state change (physical cells only).
The list is stored under the `convergence_history` key in the result payload.

### 1.2 Feature Flags / Options (Implemented)
| Flag | Default | Meaning |
| --- | --- | --- |
| `outlet_mode` | `"non_reflecting"` | Outlet BC mode: `"copy"`, `"non_reflecting"`, `"impedance"`. |
| `p_outlet` | `None` | Static outlet target used by non-reflecting/impedance BC. |
| `outlet_reflection` | `None` | Reflection coefficient for impedance BC (if used). |
| `outlet_impedance` | `None` | Acoustic impedance for impedance BC (if used). |
| `enable_friction` | `False` | Enable 1D friction source terms. |
| `friction_model` | `"swamee-jain"` | Friction correlation when enabled. |
| `friction_energy_mode` | `"wall_loss"` | Energy handling mode (`wall_loss` or `adiabatic`). |
| `roughness_m` | `0.0` | Pipe roughness for friction model. |
| `mu` | `1.8e-5` | Dynamic viscosity used for Reynolds number. |
| `use_numba_1d` | `False` | Enable the optional Numba SoA kernel. |
| `loss_coeff` | `0.0` | Optional K-loss at the cylinder/pipe boundary. |
| `pipe_role` | `"intake"` | Pipe scalar initialization (intake/exhaust). |
| `initial_Y` | `None` | Override initial scalar (must be within [0,1]). |
| `combustion.enabled` | `False` | Enable v2.1 composition-dependent combustion. |
| `heat_transfer.enabled` | `False` | Enable cylinder heat-transfer sink. |
| `enable_pumping_work` | `False` | Track pumping work (opt-in accounting output). |
| `simulation_settings.intake_plenum.enabled` | `False` | Optional intake plenum capacitance between throttle and pipe. |
| `coupling_relax_alpha` | `1.0` | Under-relaxation strength for downstream totals. |
| `coupling_relax_warmup_iters` | `0` | Warmup ramp for under-relaxation. |
| `phase_deg_intake` | `0.0` | Cam phasing offset for intake (degrees). |
| `phase_deg_exhaust` | `0.0` | Cam phasing offset for exhaust (degrees). |

### 1.3 Transient RPM Sweep (Optional)
An opt-in sweep mode can approximate a dyno ramp by stepping RPM and running a short
settle window per point. This does **not** solve each point to full periodic steady
state; it advances the coupled 0D/1D state with warm-starts to minimize extra cycles.

**Sweep config (defaults off):**
```yaml
sweep:
  enabled: false
  rpm_start: 3000
  rpm_end: 9000
  rpm_step: 250
  ramp_mode: "step"          # "step" or "linear_time"
  seconds_per_step: 0.2      # only for linear_time
  cycles_per_step: 3         # short settle per RPM point
  carry_state: true          # reuse last converged state
  record_every_step: true
  abort_on_fail: false
  throttle_position_grid: []           # optional list of throttle positions
  throttle_position_from_load: null    # optional load map (see below)
  record_part_load_metrics: false
```

**Behavior notes:**
- Initialization happens once at `rpm_start` (pipe prefill remains opt-in).
- Each RPM point runs exactly `cycles_per_step` cycles; no full steady convergence.
- `carry_state=true` warm-starts the cylinder + pipe states between RPM points.
- Each sweep step records `rpm`, `imep`, `torque`, `power`, `trapped_mass`, `ve` (if available),
  `periodicity_error`, and a `step_index`/`cycle_index` (plus `time_s` in `linear_time` mode).
- If `throttle_position_grid` or `throttle_position_from_load` is provided, the throttle
  position is updated per sweep step and part-load metrics are recorded.
- Failures are recorded with `status="failed"` and a `reason` string; execution continues
  unless `abort_on_fail=true`.

**Minimal JSON example:**
```json
{
  "sweep": {
    "enabled": true,
    "rpm_start": 3000,
    "rpm_end": 6000,
    "rpm_step": 500,
    "cycles_per_step": 3,
    "carry_state": true
  }
}
```

**Throttle sweep helper examples:**
```json
{
  "sweep": {
    "enabled": true,
    "rpm_start": 2000,
    "rpm_end": 4000,
    "rpm_step": 500,
    "throttle_position_grid": [1.0, 0.7, 0.4]
  }
}
```

```json
{
  "sweep": {
    "enabled": true,
    "rpm_start": 2000,
    "rpm_end": 4000,
    "rpm_step": 500,
    "throttle_position_from_load": {
      "load_grid": [0.0, 1.0],
      "position_grid": [0.3, 1.0]
    }
  }
}
```
Load is the normalized sweep progress from 0.0 (first step) to 1.0 (last step).

### 1.4 Fuel/BSFC (Optional Metrics Layer)
The fuel/BSFC layer is **accounting only** and does not alter combustion physics,
heat release, or any Phase-2 coupling contract. When disabled (default), no fuel
metrics are produced.

**Fuel config (defaults off):**
```yaml
fuel:
  enabled: false
  mode: "lambda"            # "lambda" or "afr"
  lambda_target: 1.0
  afr_target: 14.7
  afr_stoich: 14.7
  lhv_j_per_kg: 4.3e7
  eta_comb: 0.98
  bsfc_units: "g_per_kwh"
  clamp_lambda_min: 0.6
  clamp_lambda_max: 2.0
```

**Outputs when enabled (per cycle / per sweep step):**
- `m_air_fresh_per_cycle_kg`
- `lambda_used`, `afr_used`
- `m_fuel_per_cycle_kg`, `fuel_flow_kg_s`, `fuel_power_w`
- `brake_power_w`, `indicated_power_w`
- `bsfc_g_per_kwh`, `eta_bte`, `eta_ite`

**Part-load sweep outputs (opt-in):**
- `map_estimate`: intake MAP estimate (mean intake pipe pressure during intake stroke).
- `pumping_work`: pumping work per cycle (integral of \(p\,dV\) over intake + exhaust).
- `brake_power_w`: brake power estimate (falls back to indicated power in the advanced core).
- `bsfc_g_per_kwh`: fuel consumption per brake power (fuel must be enabled).

**Minimal JSON example:**
```json
{
  "simulation_settings": {
    "fuel": { "enabled": true, "mode": "lambda", "lambda_target": 1.0 }
  }
}
```

### 1.5 Auto-Calibration (Optional Tooling)
Auto-calibration is a **tooling-only** helper that fits a small set of meta parameters
to match a target dyno curve. It does not alter solver physics or Phase-2 contracts,
and only runs when explicitly called by a user with `calibration.enabled=true`.

**Calibration config (opt-in):**
```yaml
calibration:
  enabled: true
  pipe_role: "intake"
  cycles_per_point: 3
```

**Meta parameters it can fit:**
- `brake_model.fmep_pa` (constant FMEP, Pa) or `brake_model.fmep_curve_scale`
- `simulation_settings.fuel.eta_comb` (combustion efficiency multiplier)
- `throttle.area_exponent` (only if throttle is enabled)

**Minimal JSON example:**
```json
{
  "calibration": { "enabled": true },
  "brake_model": { "fmep_pa": 80000.0 },
  "simulation_settings": {
    "fuel": { "enabled": true, "mode": "lambda", "lambda_target": 1.0, "eta_comb": 0.98 }
  },
  "throttle": { "enabled": true, "area_exponent": 2.0 }
}
```

**Python usage snippet:**
```python
import json
from core.calibrator import calibrate_to_curve

with open("presets/v2_full_features_demo.json", "r", encoding="utf-8") as f:
    base = json.load(f)
base.setdefault("calibration", {})["enabled"] = True
base.setdefault("brake_model", {})["fmep_pa"] = 80000.0

target_points = [
    {"rpm": 3000, "brake_power_w": 80000.0},
    {"rpm": 4000, "brake_power_w": 95000.0},
]

result = calibrate_to_curve(
    base_project_config=base,
    target_points=target_points,
    fit={"fmep": True, "eta_comb": True, "throttle_k": False},
)

with open("calibrated_config.json", "w", encoding="utf-8") as f:
    json.dump(result["best_config"], f, indent=2)
```

## 2) 1D Gas Dynamics (Euler + Passive Scalar)
### 2.1 State Vector (Conserved)
\[
U = [\rho, \rho u, \rho E, \rho Y_{fresh}]
\]
- \(\rho\) [kg/m³], \(u\) [m/s]
- **Total specific energy:** \(E = e + 0.5u^2\) [J/kg]
- **Energy density:** \(\rho E\) [J/m³]
- **Fresh fraction:** \(Y_{fresh}\in[0,1]\), transported conservatively as \(\rho Y_{fresh}\)

### 2.2 Equation of State (Phase 1 Contract)
- Constant \(\gamma\) and \(R\) (ideal gas).
- Speed of sound: \(a = \sqrt{\gamma R T}\).
- Composition affects only oxygen availability / effective AFR (no variable \(\gamma/R\) yet).
- In Phase 1, \(c_p\) is **consistent** with \(\gamma\) and \(R\): \(c_p = \gamma R/(\gamma-1)\).

### 2.3 Euler Fluxes and Closure (Phase 1)
**Conserved vector:**
\[
U = [\rho, \rho u, \rho E, \rho Y]
\]
**Closure:**
\[
p = (\gamma - 1)\,\left(\rho E - 0.5\,\rho u^2\right)
\]
\[
a = \sqrt{\gamma p/\rho} = \sqrt{\gamma R T}
\]
**Flux:**
\[
F(U) = [\rho u,\ \rho u^2 + p,\ u(\rho E + p),\ \rho u Y]
\]

### 2.4 Rusanov Flux (Explicit)
At each interface:
\[
F^* = 0.5\,(F_L + F_R) - 0.5\,\alpha\,(U_R - U_L)
\]
\[
\alpha = \max(|u_L| + a_L,\ |u_R| + a_R)
\]

### 2.5 Numerical Scheme (TVD Requirement)
**Phase 1 requirement:** a TVD flux-limited method to suppress ringing.
- **Selected scheme:** MUSCL–Hancock reconstruction + Rusanov (local Lax–Friedrichs) flux.
- **Reconstruction variables:** **primitive** \((\rho, u, p, Y)\).
- **Limiter:** Minmod by default; Superbee optional.
- **Hancock predictor:** uses interface Rusanov flux divergence \(F_{i+1/2} - F_{i-1/2}\) at \(t^n\) to build \(U^{n+1/2}\) before the corrector.

**Implementation note (SoA prep):**
- The solver uses structure-of-arrays buffers internally for Numba readiness.
- Output behavior matches the reference array-of-structures path.
- Optional JIT path: `use_numba_1d` enables a Numba kernel for copy-outlet steps.
- Parity expectation: `tests/unit/test_solver1d_numba_matches_python_step.py` and
  `tests/unit/test_solver1d_numba_respects_guardrails_no_warnings.py`.

**Minmod definition (component-wise):**
\[
\text{minmod}(a,b) =
\begin{cases}
0 & ab \le 0 \\
\text{sign}(a)\min(|a|,|b|) & ab > 0
\end{cases}
\]

**Passive scalar guardrail (Phase 1):**
- After update, compute \(Y = (\rho Y)/\rho\).
- If tiny drift pushes \(Y\) slightly outside \([0,1]\), **clamp** to \([0,1]\) and recompute \(\rho Y = \rho\,Y\).
- If drift exceeds \(1\text{e-}3\) in any cell, raise an error with diagnostics (min/max \(Y\), indices).
- This clamp is a **numerical guardrail**, not physics.
- Guard runs **after** density/pressure floors (single post-guard pass), and recomposes using the floored density to keep \(\rho Y\) consistent.
- When \(\rho\) is floored from a negative value, preserve the scalar ratio using \(|\rho|\) in the pre-floor ratio.

### 2.6 Source Terms
- **Friction (Darcy–Weisbach):**
  \[
  S_{mom} = -\frac{f}{2D}\,\rho u|u|,\quad S_E = u\,S_{mom}
  \]
  - **Phase 2 correlation:** compute \(f\) from Reynolds number and roughness:
    - Laminar: \(f = 64/Re\)
    - Turbulent (Swamee-Jain): \(f = 0.25/\log_{10}^2\left(\epsilon/(3.7D) + 5.74/Re^{0.9}\right)\)
    - \(Re = \rho |u| D/\mu\)
  - **Energy mode:** `wall_loss` applies \(S_E = u S_{mom}\); `adiabatic` skips explicit \(S_E\).
- **Heat transfer (1D):**
  - Phase 1 default **OFF**: `settings.enable_1d_heat_transfer = False`.
  - If enabled, use a documented wall heat-loss model with parameters declared in settings.

### 2.7 Adaptive Time Step
\[
\Delta t = \min\left(\Delta t_{max},\; CFL \cdot \min_i \frac{\Delta x_i}{|u_i| + a_i}\right)
\]
- Defaults: `CFL = 0.5`.
- `dt_max` configurable; `dt_min` optional safety lower bound.
- Orchestrator recomputes \(\Delta t\) every step from the current 1D state.
- CFL uses **physical cells only** (ghost cells excluded) and does not mutate the input state.

### 2.8 Outlet Boundary (Phase 1)
- Default outlet uses a copy/Neumann condition (legacy behavior).
- When `p_outlet` is provided to the 1D step, the right boundary uses a simple non-reflecting
  characteristic update:
  - For subsonic outflow, hold the outgoing characteristic and set the incoming one to match
    \(p_{outlet}\).
  - For inflow or supersonic outflow, fall back to copy to avoid over-constraint.
- **Impedance mode:** optional outlet model using a reflection coefficient or impedance:
  - `outlet_mode="impedance"` with `reflection_coeff` in \([-1,1]\), or
  - `outlet_impedance` (Pa·s/m) converted using \(R = (Z - \rho a)/(Z + \rho a)\).

## 3) 0D Thermodynamics (Open Control Volume Cylinder)
### 3.1 State Tracking (Minimum)
- \(m_{total}\) [kg], \(m_{fresh}\) [kg]
- \(T_{cyl}\) [K], \(p_{cyl}\) [Pa], \(V_{cyl}\) [m³]
- \(Y_{cyl} = m_{fresh} / m_{total}\)

### 3.2 Control Volume Equations
**Mass:**
\[
\frac{dm_{total}}{dt} = \sum \dot{m}_{in} - \sum \dot{m}_{out}
\]
\[
\frac{dm_{fresh}}{dt} = \sum (\dot{m}_{in} Y_{in}) - \sum (\dot{m}_{out} Y_{out}) - m_{air,consumed}
\]

**Energy (internal-energy form):**
\[
\frac{d(m_{total} u_{int})}{dt} = \dot{Q}_{net} - p_{cyl}\frac{dV}{dt}
+ \sum (\dot{m}_{in} h_{tot,in}) - \sum (\dot{m}_{out} h_{tot,out})
\]
- \(u_{int}\) is specific internal energy [J/kg].
- \(h_{tot} = h + 0.5v^2\) at the port. Phase 1 can use \(v \approx 0\) so \(h_{tot} \approx c_p T_0\).

### 3.3 v2.1 Composition-dependent Combustion (Optional)
- Define fresh fraction \(Y_{fresh} = m_{fresh}/m_{total}\) and residual fraction
  \(X_{res} = 1 - Y_{fresh}\) (clamped to a configured range).
- Effective burn duration and efficiency:
  \[
  \text{dur}_{eff} = \text{dur}\,(1 + k_{dur} X_{res}),\quad
  \eta_{eff} = \text{clamp}\left(\eta_0 (1 - k_{\eta} X_{res}),\,\eta_{min},\,1\right)
  \]
- Heat release per cycle (simple proxy):
  \[
  Q_{total} = (m_{air}/AFR)\,LHV\,\eta_{eff}
  \]
- Wiebe burn fraction (normalized):
  \[
  x_b = \frac{1 - \exp(-a \phi^{m+1})}{1 - \exp(-a)},\quad \phi = \frac{\theta-\theta_0}{\text{dur}_{eff}}
  \]
  and \(Qdot = Q_{total}\,\frac{dx_b}{dt}\).
- Default is **disabled**; enabling may require higher `max_cycles` for heavy overlap cases.

### 3.4 Combustion Limited by Fresh Air
- Define \(AFR_{stoich}\) (default 14.7 unless fuel overrides).
- \(m_{fuel,burn} = \min(m_{fuel,inj}, m_{fresh}/AFR_{stoich})\)
- \(m_{air,consumed} = m_{fuel,burn} \cdot AFR_{stoich}\)
- \(Q_{release} = m_{fuel,burn} \cdot LHV \cdot \eta_{comb}\)
- Update \(m_{fresh} := m_{fresh} - m_{air,consumed}\)
- Wiebe phasing shapes the release, but total energy is capped by \(m_{fuel,burn}\).

### 3.5 Cam Phasing (VVT)
- Each cam lobe can be phase-shifted independently:
  - `phase_deg_intake`, `phase_deg_exhaust` (degrees).
- The effective angle is shifted before wrap:
  \[
  \theta_{eff} = (\theta - \phi_{phase}) \bmod 720
  \]
- Defaults are zero (no behavior change).

### 3.6 Cylinder Heat Transfer (Optional)
- Wall heat transfer adds a sink term based on a simple wetted-area model:
  \[
  \dot{Q}_{ht} = h\,A_{wet}\,(T_{gas} - T_{wall})
  \]
- Net heat added to the gas is:
  \[
  \dot{Q}_{net} = \dot{Q}_{comb} - \dot{Q}_{ht}
  \]
- Models:
  - `constant_h`: constant heat transfer coefficient `h_const`.
  - `woschni_simplified`: \(h\) scales with pressure, temperature, and a velocity proxy from \(dV/dt\).
- The wet area uses a piston-position approximation from bore and instantaneous volume.
- Default is **disabled**; enabling may require higher `max_cycles` to converge.

## 4) Coupling Interface (Critical Contract)
**Phase-2 contract summary (implemented):**
- Direction uses stagnation totals \(p_0\) vs \(p_{0,down}\) with hysteresis when available; falls back to static if not.
- K-loss is bidirectional, reduces \(|\dot{m}|\) only, never flips sign, and does **not** scale downstream totals.
- Ghost inversion brackets Mach from \(M=0\), supports \(\dot{m}\rightarrow 0\), and post-checks the final error.
- Outlet BC is enforced via a ghost-right interface state (non-reflecting / impedance), not by mutating interior cells.
- Scalar guard runs post-guard and recomposes \(\rho Y\) using the floored density; negative-\(\rho\) floors preserve the scalar ratio.
- CFL ignores ghost cells and has no side effects; Cd is applied exactly once in \(A_{eff}\).
### 4.1 Valve/Port Effective Area
\[
A_{eff} = C_d A_{valve}
\]
- **Curtain model (default):** \(A_{valve} = N_{valves} \pi D_{seat} \cdot lift\).
- **Fixed-area option:** \(A_{valve} = constant\).
- Units: \(D_{seat}\) [m], \(lift\) [m], \(A_{eff}\) [m²].

### 4.2 Isentropic Nozzle Mass Flow (Phase 1)
**Inputs:** \(p_0, T_0, p_{down}, A_{eff}, \gamma, R\).

**Note on Cd:** Cd is already **baked into** \(A_{eff}\). Do **not** multiply by Cd again.
**Phase 2 totals convention:** \(p_0, T_0\) are **stagnation** values. Static \(p, T\) are
used for \(p_{down}\); stagnation totals on the downstream side are computed from the
pipe cell \((p, T, u)\) when backflow occurs. Phase 1 may still treat \(p_0 \approx p\),
\(T_0 \approx T\) if configured.

Define:
\[
 c_p = \frac{\gamma R}{\gamma - 1}
\]
\[
 pr_{crit} = \left(\frac{2}{\gamma+1}\right)^{\gamma/(\gamma-1)}
\]

**Operational backflow rule (signed convention):**
- If downstream totals are available \((p_{0,down})\), determine direction by **stagnation pressures**:
  - If \(p_0 \ge p_{0,down}\): forward (cyl → pipe).
  - If \(p_0 < p_{0,down}\): reverse (pipe → cyl).
- Use a small hysteresis band around \(p_0 \approx p_{0,down}\) to avoid chattering; within the band, fall back to static comparison.
- If downstream totals are not provided, fall back to static comparison \(p_{down} \le p_0\).
- Forward: use upstream totals \((p_0, T_0, Y_0)\) and downstream static \(p_{down}\); \(\dot{m} = +\dot{m}_{mag}\).
- Reverse: use upstream totals from the downstream side \((p_{0,rev}, T_{0,rev}, Y_{0,rev})\) and downstream static from the original upstream side; \(\dot{m} = -\dot{m}_{mag}\).
- \(\dot{H}\) and \(\dot{Y}\) always use **upstream totals** of the actual flow direction:
  - \(\dot{H} = \dot{m}\,h_{tot,upstream}\) with \(h_{tot} \approx c_p T_0\) in Phase 1.
  - \(\dot{Y} = \dot{m}\,Y_{upstream}\).

**Choking criterion:** choked if \(p_{down}/p_0 \le pr_{crit}\).

**Choked flow:**
\[
\dot{m} = A_{eff} \, p_0 \, \sqrt{\frac{\gamma}{R T_0}}\,\left(\frac{2}{\gamma+1}\right)^{\frac{\gamma+1}{2(\gamma-1)}}
\]

**Subsonic flow:**
\[
pr = \frac{p_{down}}{p_0}
\]
\[
\dot{m} = A_{eff} \, p_0 \, \sqrt{\frac{2\gamma}{R T_0 (\gamma-1)}\,\left(pr^{2/\gamma} - pr^{(\gamma+1)/\gamma}\right)}
\]

These equations compute \(\dot{m}_{mag}\); the signed \(\dot{m}\) is assigned by the backflow swap rule in §4.2.

### 4.3 Boundary Flux Application (Phase 1 Recipe)
**Option B (selected): ghost-cell construction + Rusanov flux.**

Define:
- \(A_{face}\) = cross-sectional area of the pipe-end finite-volume face (**not** valve area).

Ghost primitive state (upstream reservoir model):
- Use stagnation totals \((p_0, T_0)\) on the **upstream** side and invert isentropic
  relations to obtain static \((p, T, u)\) for the ghost.
- The inversion supports \( \dot{m} \to 0 \) by a small-M linear approximation and brackets Mach with \(M \in [0, 0.999]\) using a monotone expansion.
- Final inversion error is checked; inconsistent targets raise a diagnostic error.
- Phase 2 ghost uses the inverted static \((p_g, T_g, u_g)\); Phase 1 fallback uses
  \(p_g = p_{0,upstream}\), \(T_g = T_{0,upstream}\), \(u_g = \dot{m}/(\rho_g A_{face})\).
- \(\rho_g = p_g/(R T_g)\), \(Y_g = Y_{0,upstream}\).

Then:
- Convert ghost primitive → ghost conserved using the same closure as the interior.
- Use the standard Rusanov numerical flux between ghost and the first interior cell.
- Apply that flux to update the boundary cell exactly like any interior face.
- **No direct pressure forcing** at the boundary.

**Local losses (optional Phase 2):**
- Apply a loss coefficient \(K\) at the pipe entrance/exit as an added static drop:
  \(\Delta p = K \cdot 0.5 \rho u^2\).
- Implemented as an adjustment to the downstream static pressure used for nozzle flow:
  - Forward: \(p_{down,eff} = p_{down} + \Delta p\)
  - Reverse: \(p_{down,eff} = \max(p_{res} + \Delta p, p_{min})\)
- Direction is still decided by \(p_0\) vs \(p_{0,down}\); K-loss does **not**
  modify downstream totals.
- If face area is available, use \(u_{face} = \dot{m}/(\rho A_{face})\) to compute \(\Delta p\);
  otherwise fall back to a provided \(u_{down}\) approximation.
- K-loss reduces \(|\dot{m}|\) only and **must not** flip the flow direction.

### 4.4 Junction Model v2 (Optional)
- Junction mixing uses inflow mass-weighted totals:
  - \(T_{0,mix}\) from mass-weighted stagnation enthalpy \(h_0 = c_p T_0\).
  - \(Y_{mix}\) from mass-weighted scalar mixing.
  - \(p_{0,mix}\) as a mass-weighted average of incoming totals.
- Outgoing legs use the mixed totals as upstream conditions.

**Junction capacitance (optional, off by default):**
- Enables a 0D reservoir at the junction to smooth strong pulses while conserving mass, energy, and scalar.
- State variables: \(m\), \(E\), and \(mY\) in a fixed volume \(V\) (reservoir \(v \approx 0\)).
- Update per substep:
  - \(dm = \sum \dot{m}_{in}\,dt - \sum \dot{m}_{out}\,dt\)
  - \(d(mY) = \sum \dot{m}_{in} Y_{in}\,dt - \sum \dot{m}_{out} Y_{out}\,dt\)
  - \(dE = \sum \dot{m}_{in} h_{0,in}\,dt - \sum \dot{m}_{out} h_{0,out}\,dt\)
- Recover state from \(m, E, V\) via EOS; clamp \(p \ge p_{min}\), \(T \ge T_{min}\), and \(Y \in [0,1]\).
- Optional under-relaxation \(\alpha \in [0,1]\) can be applied to the state update.
- When disabled, the algebraic mixing above remains the default behavior.

Example JSON (enable junction capacitance):
```json
{
  "junctions": [
    {
      "name": "exh_4_to_1",
      "legs": ["cyl1", "cyl2", "cyl3", "cyl4", "collector"],
      "capacitance": {
        "enabled": true,
        "volume_m3": 0.0009,
        "p_min_Pa": 2000.0,
        "T_min_K": 200.0,
        "under_relax_alpha": 0.6
      }
    }
  ]
}
```

### 4.5 Throttle (Optional)
- Enables an intake throttle (butterfly) as a nozzle boundary between ambient and the intake pipe.
- Parameters (defaults preserve current behavior):
  - `throttle.enabled` (default `False`)
  - `throttle.position` in \([0,1]\) (default `1.0`, WOT)
  - `throttle.body_diam_m` (required when enabled)
  - `throttle.cd` (default `1.0`)
  - `throttle.area_exponent` (default `2.0`)
  - `throttle.rate_limit_per_s` (optional, default `null`): max position change per second
  - `throttle.safety_clamps` (optional, default `False`)
  - Optional ambient totals: `throttle.p0_amb_Pa`, `throttle.T0_amb_K`, `throttle.Y0_amb`
- Effective area:
  - \(A_{max} = \pi D^2/4\)
  - \(A_{eff} = C_d A_{max} \cdot \mathrm{clamp}(pos,0,1)^{n}\)
- Boundary behavior follows the Phase-2 nozzle contract (direction by stagnation totals + hysteresis).
- Enables part-throttle pumping losses without altering core coupling contracts.
- If `rate_limit_per_s` is set, the commanded position is filtered with a first-order slew limiter.
- If `safety_clamps` is enabled, position is clamped to \([0,1]\) and `area_exponent` is clamped to \(\ge 1\).

Example JSON:
```json
{
  "throttle": {
    "enabled": true,
    "position": 0.35,
    "body_diam_m": 0.06,
    "area_exponent": 2.0,
    "cd": 1.0
  }
}
```

Example JSON (rate limit + clamps):
```json
{
  "throttle": {
    "enabled": true,
    "position": 0.4,
    "body_diam_m": 0.06,
    "area_exponent": 2.0,
    "cd": 1.0,
    "rate_limit_per_s": 3.0,
    "safety_clamps": true
  }
}
```

### 4.6 Pipe Prefill (Optional)
- Allows setting the initial pipe state for faster convergence.
- If enabled, physical cells are initialized from the role-specific settings.
- Defaults when enabled: intake \(Y=1\), exhaust \(Y=0\) with higher \(T\) (e.g., 700 K).
- If `auto` is enabled, intake uses ambient \(p/T\) and exhaust uses ambient \(p\) with
  `exhaust_prefill_T_K` for temperature.

Example JSON:
```json
{
  "pipe_prefill": {
    "enabled": true,
    "intake": { "p_Pa": 101325.0, "T_K": 300.0, "Y": 1.0 },
    "exhaust": { "p_Pa": 101325.0, "T_K": 700.0, "Y": 0.0 }
  }
}
```

Example JSON (auto defaults):
```json
{
  "pipe_prefill": {
    "enabled": true,
    "auto": true,
    "exhaust_prefill_T_K": 700.0
  }
}
```

### 4.7 Intake Plenum Capacitance (Optional)
- Optional 0D plenum capacitance between ambient/throttle and the intake pipe inlet.
- When enabled, flow path is: ambient -> throttle nozzle (if enabled) -> plenum -> pipe inlet nozzle.
- Plenum update uses:
  \[
  \frac{dm}{dt} = \dot{m}_{in} - \dot{m}_{out},\quad
  \frac{dE}{dt} = \dot{m}_{in}h_{0,in} - \dot{m}_{out}h_{0,out} - \dot{Q}_{ht},\quad
  \frac{d(mY)}{dt} = \dot{m}_{in}Y_{in} - \dot{m}_{out}Y_{plenum}
  \]
- The plenum is treated as a static reservoir (\(u \approx 0\)), so \(p_0 \approx p\) and \(T_0 \approx T\).
- Floors `p_floor_pa`/`t_floor_k` clamp state updates; `under_relax_alpha` applies only to the plenum \(p/T\) update.
- \( \dot{Q}_{ht} \) is optional and defaults to zero.

Example JSON:
```json
{
  "simulation_settings": {
    "intake_plenum": {
      "enabled": true,
      "volume_m3": 0.004,
      "p_init_pa": 101325.0,
      "t_init_k": 300.0,
      "y_init": 1.0,
      "p_floor_pa": 20000.0,
      "t_floor_k": 200.0,
      "under_relax_alpha": 1.0
    }
  }
}
```

### 4.8 Valve-Closed Wall BC (Optional)
- When enabled and \(A_{eff} < \epsilon\), the valve boundary becomes a reflective wall:
  \(u_g = -u\), \(p_g = p\), \(\rho_g = \rho\), \(Y_g = Y\).
- Ensures \(\dot{m} \approx 0\) for nearly closed valves without invoking nozzle inversion.

Example JSON:
```json
{
  "valve_closed_wall_bc": {
    "enabled": true,
    "area_eps_m2": 1e-7
  }
}
```

### 4.9 Thermally Perfect Gas (Optional)
- Enable NASA7-based \(c_p(T)\), \(h(T)\), \(e(T)\), and \(\gamma(T)\).
- Mixture uses \(Y_{fresh}\) as a blend between fresh air and a burned-gas proxy.
- \(e(T)\) inversion uses Newton-Raphson with clamped temperature bounds.

Example JSON:
```json
{
  "simulation_settings": {
    "cp_model": "nasa7"
  }
}
```

### 4.10 Wall Thermal (Optional)
- Optional lumped-capacitance wall temperature for pipe/junction heat transfer.
- Wall state evolves as:
  \[
  \frac{dT_{wall}}{dt} = \frac{hA\,(T_{gas} - T_{wall})}{m_{wall} c_{p,wall}}
  \]
- When enabled, heat transfer uses the dynamic \(T_{wall}\) instead of a fixed wall temperature.

Example JSON:
```json
{
  "simulation_settings": {
    "wall_thermal": {
      "enabled": true,
      "m_wall_kg": 2.0,
      "cp_wall_j_per_kgk": 500.0,
      "h_w_per_m2k": 50.0,
      "area_m2": 0.25,
      "twall_init_k": 450.0,
      "twall_min_k": 300.0,
      "twall_max_k": 900.0
    }
  }
}
```

### Numerical Stabilization (Optional): Under-relaxation
- Optional under-relaxation can be applied to downstream totals \((p_{0,down}, T_{0,down}, Y_{0,down})\)
  fed into the 0D coupling step.
- Defaults are off (`coupling_relax_alpha = 1.0`, `coupling_relax_warmup_iters = 0`).

### Optional Feature Flags (Implemented)
- `use_numba_1d` (default `False`): enable Numba SoA kernel for the 1D step.
- `combustion.enabled` (default `False`): v2.1 Wiebe-based combustion tied to \(Y_{fresh}\).
- `heat_transfer.enabled` (default `False`): cylinder wall heat-transfer sink.
- `outlet_mode` (default `"non_reflecting"`): `"copy"`, `"non_reflecting"`, or `"impedance"` (see §2.8).
- `throttle.enabled` (default `False`): optional intake throttle boundary.
- `pipe_prefill.enabled` (default `False`): optional initial pipe state override.
- `valve_closed_wall_bc.enabled` (default `False`): reflective wall when valve area is near zero.
- `cp_model` (default `"constant"`): `"constant"` or `"nasa7"` thermally perfect gas.
- `wall_thermal.enabled` (default `False`): dynamic wall temperature for pipe/junction heat transfer.
- `simulation_settings.intake_plenum.enabled` (default `False`): intake plenum capacitance between throttle and pipe.

**Indexing convention:** in the coupled 1D pipe, `U[0]` is the left ghost cell, `U[-1]` is the right ghost cell, and physical cells are `U[1:-1]`. The downstream static state \((p_{down}, T_{down}, Y_{down})\) is sampled from `U[1]`.

**Note:** Any clamping of \(u_g\) is a **numerical guardrail** and must be minimal and documented.

## 5) Orchestrator: Synchronization & Convergence
### 5.1 Time Integration (Single Global \(\Delta t\))
At each step:
1. Update valve lift/area from cam timing.
2. Compute nozzle \(\dot{m}/\dot{H}/\dot{Y}\) at intake/exhaust interfaces.
3. Advance cylinder control volume using \(dm/dt\), \(d(m u_{int})/dt\), and \(dV/dt\).
4. Advance 1D network by one TVD step with source terms + boundary fluxes.

**Pipe mixture initialization (Phase 2):**
- `pipe_role="intake"` initializes \(Y=1.0\); `pipe_role="exhaust"` initializes \(Y=0.0\).
- `initial_Y` can override the default (must be within \([0,1]\)).

### 5.2 Cycle-to-Cycle Convergence
Stop when **both** are satisfied:
- Relative error of trapped mass at IVC < **0.5%** between cycles.
- Relative error of indicated work \(\oint p\,dV\) over 720° < **0.5%** between cycles.
- Periodicity metric on the 1D state (L2 norm of \(U_{end}-U_{start}\) over physical cells)
  below `periodicity_tol` for `periodicity_required` consecutive cycles.

**Convergence monitor output (per cycle):**
- `k`: cycle index.
- `err_trapped_mass`: relative change in trapped mass vs previous cycle.
- `err_imep`: relative change in IMEP vs previous cycle.
- `err_periodicity_1d`: L2 norm of \(U_{end}-U_{start}\) over physical cells, normalized by \(||U_{start}||\).

## 6) Outputs & Derived Results
- **IVC definition:** IVC occurs when intake valve effective area \(A_{eff}\) crosses to zero on the closing edge (or at a fixed crank angle if specified in settings).
- \(\rho_{ambient} = p_{amb}/(R T_{amb})\).
- **VE (per-cylinder, averaged):**
  \[
  VE_{real} = \frac{m_{fresh,IVC}}{\rho_{ambient} V_{disp,per\,cyl}}
  \]
  For multi-cylinder, compute per-cylinder VE and report the average.
- **Residual fraction:**
  \[
  res\_frac = 1 - \frac{m_{fresh}}{m_{total}}\Big|_{IVC}
  \]

### 6.1 Indicated Work Discretization
Per cylinder:
\[
W_{ind} = \sum_i 0.5\,(p_i + p_{i+1})\,(V_{i+1} - V_i)
\]
Total indicated work (multi-cylinder): multiply by `num_cylinders`.

### 6.2 Histories & Probes
Provide histories for:
- \(p_{cyl}, T_{cyl}, \dot{m}_{intake}, \dot{m}_{exhaust}, Y_{cyl}\)
- Selected pipe probes (pressure, velocity, \(Y_{fresh}\)).

## 7) Testing & Verification Requirements
### Unit Tests
- Nozzle choking regime correctness.
- Conservative transport of \(\rho Y_{fresh}\) (no negative \(Y\), stable bounds with guardrail clamp).
- CFL \(\Delta t\) computation decreases when \(|u|\) or \(a\) increases.
- Primitive ↔ conserved roundtrip within tolerance.

### Integration Tests (marker: `integration`)
- Intake pipe + cylinder shows ram charging (VE > 1 possible).
- Exhaust blowdown yields expected wave travel time (no NaN/inf).

---
**Document Version:** v2.0 (Phase 1)
