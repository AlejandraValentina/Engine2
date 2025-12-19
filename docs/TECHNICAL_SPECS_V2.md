# PyWaveDyn v2.0 — Technical Specs (Advanced Coupled Physics)

## 0) Scope & Compatibility
- **Parallel core:** v2.0 lives under `core/advanced/` and does **not** replace the v1.0 core.
- **Product naming:** v1.0 remains **Quick Dyno**. v2.0 is the **Advanced Physics Core**.
- **Backward compatibility:** presets JSON must remain compatible via defaults and tolerant parsing.

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

### 2.3 Numerical Scheme (TVD Requirement)
**Phase 1 requirement:** a TVD flux-limited method to suppress ringing.
- **Selected scheme:** MUSCL–Hancock reconstruction + Rusanov (local Lax–Friedrichs) flux.
- **Limiter:** Minmod by default; Superbee is optional.

### 2.4 Source Terms
- **Friction (Darcy–Weisbach):**
  \[
  S_{mom} = -\frac{f}{2D}\,\rho u|u|,\quad S_E = u\,S_{mom}
  \]
- **Heat transfer (1D):**
  - Phase 1 default **OFF**: `settings.enable_1d_heat_transfer = False`.
  - If enabled, use a documented wall heat-loss model with parameters declared in settings.

### 2.5 Adaptive Time Step
\[
\Delta t = \min\left(\Delta t_{max},\; CFL \cdot \min_i \frac{\Delta x_i}{|u_i| + a_i}\right)
\]
- Defaults: `CFL = 0.5`.
- `dt_max` configurable; `dt_min` optional safety lower bound.
- Orchestrator recomputes \(\Delta t\) every step from the current 1D state.

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

### 3.3 Combustion Limited by Fresh Air
- Define \(AFR_{stoich}\) (default 14.7 unless fuel overrides).
- \(m_{fuel,burn} = \min(m_{fuel,inj}, m_{fresh}/AFR_{stoich})\)
- \(m_{air,consumed} = m_{fuel,burn} \cdot AFR_{stoich}\)
- \(Q_{release} = m_{fuel,burn} \cdot LHV \cdot \eta_{comb}\)
- Update \(m_{fresh} := m_{fresh} - m_{air,consumed}\)
- Wiebe phasing shapes the release, but total energy is capped by \(m_{fuel,burn}\).

## 4) Coupling Interface (Critical Contract)
### 4.1 Valve/Port Effective Area
\[
A_{eff} = C_d A_{valve}
\]
- **Curtain model (default):** \(A_{valve} = \pi D_{seat} \cdot lift\).
- **Fixed-area option:** \(A_{valve} = constant\).
- Units: \(D_{seat}\) [m], \(lift\) [m], \(A_{eff}\) [m²].

### 4.2 Compressible Nozzle Flow (Phase 1 Only)
**Inputs:**
- Upstream totals: \(p_0, T_0, Y_0\)
- Downstream static pressure: \(p_{down}\)
- \(A_{eff}, \gamma, R, c_p\)

**Outputs (positive upstream → downstream):**
- \(\dot{m}\)
- \(\dot{H} = \dot{m}\,h_{tot,up}\) (Phase 1: \(h_{tot} \approx c_p T_0\))
- \(\dot{Y} = \dot{m}\,Y_0\)

**Choking condition:**
\[
\left(\frac{p_{down}}{p_0}\right)_{crit} = \left(\frac{2}{\gamma+1}\right)^{\gamma/(\gamma-1)}
\]
- If \(p_{down}/p_0 \le (p_{down}/p_0)_{crit}\), use the choked formula.
- Else, use the subsonic formula.

### 4.3 Boundary Application to 1D (Phase 1)
- Use **flux-consistent ghost-cell boundary updates** from nozzle outputs.
- Apply nozzle fluxes to \([\rho, \rho u, \rho E, \rho Y_{fresh}]\) at the boundary face.
- **Do not** force pressure directly at the boundary.

### 4.4 Mixing Logic (Sign-Consistent)
- Flow direction is defined by \(\dot{m}\) sign (or port velocity sign).
- Inflow to cylinder (\(\dot{m} > 0\)): use \(Y_{in} = Y_{pipe}\).
- Backflow to pipe (\(\dot{m} < 0\)): use \(Y_{out} = Y_{cyl}\).
- Enables emergent EGR/reversion.

## 5) Orchestrator: Synchronization & Convergence
### 5.1 Time Integration (Single Global \(\Delta t\))
At each step:
1. Update valve lift/area from cam timing.
2. Compute nozzle \(\dot{m}/\dot{H}/\dot{Y}\) at intake/exhaust interfaces.
3. Advance cylinder control volume using \(dm/dt\), \(d(m u_{int})/dt\), and \(dV/dt\).
4. Advance 1D network by one TVD step with source terms + boundary fluxes.

### 5.2 Cycle-to-Cycle Convergence
Stop when **both** are satisfied:
- Relative error of trapped mass at IVC < **0.5%** between cycles.
- Relative error of indicated work \(\oint p\,dV\) over 720° < **0.5%** between cycles.

## 6) Outputs & Derived Results
- **VE as result:**
  \[
  VE_{real} = \frac{m_{fresh,IVC}}{\rho_{ambient} V_{disp}}
  \]
- **Residual fraction:** \(1 - m_{fresh}/m_{total}\) at IVC (or defined compression start).
- Provide histories for:
  - \(p_{cyl}, T_{cyl}, \dot{m}_{intake}, \dot{m}_{exhaust}, Y_{cyl}\)
  - Selected pipe probes (pressure, velocity, \(Y_{fresh}\)).

## 7) Testing & Verification Requirements
### Unit Tests
- Nozzle choking regime correctness.
- Conservative transport of \(\rho Y_{fresh}\) (no negative \(Y\), stable bounds).
- CFL \(\Delta t\) computation decreases when \(|u|\) or \(a\) increases.

### Integration Tests (marker: `integration`)
- Intake pipe + cylinder shows ram charging (VE > 1 possible).
- Exhaust blowdown yields expected wave travel time (no NaN/inf).

---
**Document Version:** v2.0 (Phase 1)
