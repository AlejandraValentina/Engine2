# PyWaveDyn Software Design Document (SDD)

## 1. Arquitectura General

PyWaveDyn sigue un flujo MVC simplificado: la GUI PySide6 captura la configuración del usuario, la persiste/recupera en JSON mediante el modelo jerárquico `Engine`, y ejecuta los solucionadores físicos 0D/1D. Los resultados vuelven a la GUI para gráficas (dyno, scope, análisis), audio y optimización.

```
[GUI PySide6]
   ├─ Árbol de proyecto + panel de propiedades (edita objetos Engine/*)
   ├─ Tabs: Overview, Dyno/Pro Dyno, Analysis Data, Optimizer, Scope
   └─ Botones/acciones → invocan solvers
        ├─ core/thermo.py  (0D ciclo Otto + VE + fricción + knock)
        ├─ core/simulator.py (1D ondas en tubos con Lax–Wendroff)
        └─ core/numerics.py  (kernels Numba: flujos Euler, Lax–Wendroff, mdot)
              └─ Salidas → GUI (plots/tablas) + audio_generator (WAV)
```

## 2. Diccionario de Módulos

### main.py
- **Responsabilidad:** Punto de entrada Qt; crea `QApplication` y `MainWindow`.
- **Entradas/Salidas:** Inicia el loop de eventos; no recibe parámetros externos.

### core/engine_components.py
- **Responsabilidad:** Dataclasses del motor (Block, CylinderHead, Camshaft, Intake/Exhaust, Supercharger, Friction con coeficientes Chen–Flynn, Fuel, Combustion, SimulationSettings, Engine) con `to_dict`/`from_dict`, cálculo de desplazamiento y CR geométrico.
- **Claves:** `Engine.from_dict`, `Engine.save_to_file`, `Camshaft.get_lift`, `Block.displacement_cc`, `Engine.calculate_geometric_cr`.
- **Entradas/Salidas:** Configuración estructurada ↔ JSON; utilidades geométricas.

### core/thermo.py
- **Responsabilidad:** Simulador termodinámico 0D: ciclo Otto faseado, VE dinámica (cam + Mach + tuning + pérdidas de tubería y CFM), combustión Wiebe parametrizada, knock, fricción Chen–Flynn + accesorios, métricas BMEP/VE/airflow/knock.
- **Claves:** `piston_geometry`, `wiebe_function`, `CylinderSimulator.run_cycle` (modo rápido calibrado).
- **Entradas/Salidas:** Recibe `Engine` + rpm; devuelve trazas y agregados: `pressure`, `volume`, `torque`, `mean_torque_nm`, `mean_power_hp`, `bmep_bar`, `ve`, `airflow_cfm`, `knock_warning`.

### core/simulator.py
- **Responsabilidad:** Solver 1D para tubos; construye malla, aplica BCs de celdas fantasma (válvula/cilindro + salida transmisiva), integra con Lax–Wendroff y clamps de estabilidad.
- **Claves:** `PipeSolver.apply_boundary_conditions`, `PipeSolver.get_time_step`, `PipeSolver.step`.
- **Entradas/Salidas:** Estado conservado `U[:, rho, rho*u, rho*E]` ↔ evolución temporal.

### core/numerics.py
- **Responsabilidad:** Kernels Numba para Euler 1D, Lax–Wendroff y flujo isentrópico de válvula.
- **Claves:** `flux_vector`, `source_terms`, `lax_wendroff_step`, `calculate_mass_flow_rate`.
- **Entradas/Salidas:** Estados ↔ flujos; mdot direccional con choking.

### acoustics/audio_generator.py
- **Responsabilidad:** Re-muestreo (interp1d) de presión, filtrado pasa-altas, normalización y guardado WAV.

### gui/main_window.py
- **Responsabilidad:** Shell Qt con árbol de proyecto, propiedades dinámicas, tabs de visualización y optimizador, controles de simulación/recording, resumen HTML.
- **Claves:** `refresh_tree`, `update_properties_panel`, `run_dyno_sweep`, `run_pro_dyno_sweep`, `run_optimization_sweep`, `update_overview`.

### tests/
- **Responsabilidad:** Suite unitaria/integración (identidades HP↔Torque, tendencias de tuning, bandas de sanidad BMEP/VE, regresiones multi-motor, fixtures deterministas y seeds en `conftest.py`).

## 3. Física Implementada

### 3.1 Ciclo 0D faseado (4 tiempos)
- Ángulo 0–720° con máscaras no solapadas:
  - **Intake:** `angle < IVC` (IVC desde LSA/advance, acotado 180–360°).
  - **Compresión:** `IVC ≤ angle < 360` usando `P*V^γ = const` con volumen real en IVC.
  - **Potencia:** `360 ≤ angle < EVO` (EVO acotado 400–720°) sumando ΔP de combustión.
  - **Escape:** `angle ≥ EVO`, presión cercana a backpressure.
- Volumen: `piston_geometry` devuelve V y dV; se clampa a >0 para evitar NaN.

### 3.2 Combustión (Wiebe)
- Inicio: `start_angle = 360 - combustion.ignition_advance`.
- Duración: `combustion.burn_duration` grados.
- Energía: `Q_total = m_fuel * fuel.energy_density`; `Q_effective = Q_total * combustion.thermal_efficiency`.
- Fracción liberada: `x(θ)=1-exp(-a*((θ-start)/duration)^(m+1))` (coef estándar a=5, m=2).
- Incremento de presión en potencia: `(γ-1) * Q_effective * x_burn / V`.

### 3.3 Volumetric Efficiency (VE) dinámica
- Curva base VE (tres puntos) centrada en `cam.peak_rpm` y modulada por duración de leva (más duración → pico VE mayor). Forma `[idle, peak, peak+1500]` escalada por `peak_ve` derivado de intake_duration.
- Choking por Mach Index: área efectiva de válvulas (diámetro, nº válvulas, eficiencia de puerto) vs área de pistón; velocidad de gas = V_pistón * (A_pistón / A_efectiva); umbral de Mach = `head.mach_tolerance`; penalización suave si se supera; VE ≥ 0.4.
- Restricción por CFM total: `total_capacity = head.port_flow_cfm * intake_valves * num_cyl * port_flow_efficiency` comparado con throttle_cfm; penalización √(capacidad/requerido) si se estrangula.
- Pérdidas L/D de tuberías: factores lineales por runner/header (L/D * 0.002) aplicados a VE; tuning acústico de escape/intake con boost ±15% según longitud armónica.

### 3.4 Knock
- CR dinámica desde IVC y P_manifold; octanaje desde `fuel.octane_rating`.
- Si `octane_req > fuel.octane`, se reduce potencia (retardo implícito) y se marca `knock_warning` en salidas/GUI.

### 3.5 Fricción (FMEP) y bombeo
- FMEP Chen–Flynn configurable por usuario: `FMEP = A + B·RPM + C·RPM²` (kPa) usando coeficientes de `engine.friction`.
- Multiplicadores de accesorios (bomba agua, alternador, dirección, ventilador) se suman como torque adicional dependiente de RPM.
- Par de fricción restado al indicado y limitado para evitar resultados negativos.

### 3.6 Airflow y métricas
- Airflow CFM: `(CID * RPM * VE) / 3456` (CID desde displacement_cc). VE reportada en % y Mach index devuelto.
- BMEP: `BMEP = 4π·T / (Vd_m3) / 100000` (bar) para trazabilidad de torque.

### 3.7 Dinámica 1D en tubos
- Esquema Lax–Wendroff predictor-corrector (`lax_wendroff_step`) con términos fuente de fricción y variación de área.
- **Celdas fantasma:**
  - Inlet abierto: estado ideal-gas con `p_cyl`/`T_cyl`, energía acotada; se "empuja" celda 1.
  - Inlet cerrado: copia densidad/energía de celda 1 e invierte momento (pared reflectiva) para evitar presión atrapada.
  - Outlet: copia transmisiva `U[-1]=U[-2]` para minimizar reflexiones.
- CFL: `dt` desde `max(|u|+a)` recalculado tras aplicar BCs; clamps de densidad/energía para estabilidad.

## 4. Estructura de Proyecto (carpeta raíz)

```
├─ main.py
├─ TECHNICAL_DOCS.md
├─ DOCUMENTATION.md
├─ core/
│   ├─ engine_components.py
│   ├─ thermo.py
│   ├─ simulator.py
│   └─ numerics.py
├─ gui/
│   ├─ main_window.py
│   └─ widgets/scope_widget.py
├─ acoustics/audio_generator.py
├─ requirements.txt / requirements-dev.txt
├─ pytest.ini
├─ tests/ (unit + integration)
├─ presets JSON (honda_k20.json, chevy.json, ferrari_355_v12.json, ferrari_f1.json)
└─ ci.sh
```

## 5. Guía de Mantenimiento y Debugging

- **NaNs/Instabilidad 1D:** Revisar clamps en `PipeSolver.step` y orden: aplicar BCs antes de `get_time_step`. Verificar unidades SI en longitudes/diámetros.
- **Línea plana en Scope/Dyno:** Confirmar que `apply_boundary_conditions` usa valve_area > 0 y que se actualiza `self.U[-1]`. Revisar amplitud de fuente (p_cyl, área válvula).
- **Potencia anómala 0D:** Revisar IVC/EVO (LSA/advance), `combustion` (eficiencia/duración/avance/AFR), coeficientes FMEP, `port_flow_efficiency`, `mach_tolerance`, y octanaje vs knock.
- **Persistencia:** `Engine.save_to_file`/`from_dict` incluyen Combustion, Friction (A/B/C), Fuel, peak_rpm, VE/port params; tras cargar, llamar a `refresh_tree` para re-vincular referencias.
- **Pruebas:** `pytest -q` (rápidas); `pytest -q -m integration` requiere NumPy y valida tendencias/bandas.

## 6. Roadmap / Deuda Técnica

- Acoplar solver 0D↔1D en tiempo real con intercambio de flujo/energía bidireccional.
- Mejorar audio (muestreo adaptativo, paneo/HRIR) y profiling numérico.
- Optimizar GUI para presets de combustible/octanaje y límites de knock en el optimizador.
- Añadir trazas de logging estructurado en lugar de prints de debug en solvers.

## 7. Limpieza

Archivos temporales o superseded por la GUI/tests que deben eliminarse del repo final:
- `test_solver.py`
- (Si existiera) `validate_physics.py` u otros scripts ad-hoc de desarrollo manual.
