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

## 4) Coupling Interface (Critical Contract)
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
