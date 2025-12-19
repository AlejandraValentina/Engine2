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
- This clamp is a **numerical guardrail**, not physics.

### 2.6 Source Terms
- **Friction (Darcy–Weisbach):**
  \[
  S_{mom} = -\frac{f}{2D}\,\rho u|u|,\quad S_E = u\,S_{mom}
  \]
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

### 4.2 Isentropic Nozzle Mass Flow (Phase 1)
**Inputs:** \(p_0, T_0, p_{down}, A_{eff}, \gamma, R\).

**Note on Cd:** Cd is already **baked into** \(A_{eff}\). Do **not** multiply by Cd again.

Define:
\[
 c_p = \frac{\gamma R}{\gamma - 1}
\]
\[
 pr_{crit} = \left(\frac{2}{\gamma+1}\right)^{\gamma/(\gamma-1)}
\]

**Operational backflow rule (signed convention):**
- If \(p_{down} \le p_0\): use upstream totals \((p_0, T_0, Y_0)\) and downstream static \(p_{down}\). Compute \(\dot{m}_{mag}\) from the formulas below and set \(\dot{m} = +\dot{m}_{mag}\).
- If \(p_{down} > p_0\): **swap roles**. Use upstream totals from the downstream side \((p_{0,rev}, T_{0,rev}, Y_{0,rev})\) and downstream static \(p_{down,rev}\) from the original upstream side. Compute \(\dot{m}_{mag}\) with the same formulas and set \(\dot{m} = -\dot{m}_{mag}\).
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
- \(p_g = p_{0,upstream}\)
- Phase 1 approximates \(p_0 \approx p\) for the reservoir ghost; later phases may distinguish \(p_0\) and \(p\) explicitly.
- \(T_g = T_{0,upstream}\)
- \(\rho_g = p_g/(R T_g)\)
- \(u_g = \dot{m}/(\rho_g A_{face})\) (signed)
- \(Y_g = Y_{0,upstream}\)

Then:
- Convert ghost primitive → ghost conserved using the same closure as the interior.
- Use the standard Rusanov numerical flux between ghost and the first interior cell.
- Apply that flux to update the boundary cell exactly like any interior face.
- **No direct pressure forcing** at the boundary.

**Note:** Any clamping of \(u_g\) is a **numerical guardrail** and must be minimal and documented.

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
