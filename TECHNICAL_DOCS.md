# PyWaveDyn Software Design Document (SDD)

## 1. Arquitectura General

PyWaveDyn implementa un flujo MVC simplificado donde la GUI PySide6 captura la configuración del usuario, la serializa en el modelo de datos jerárquico y alimenta a los solucionadores físicos 0D/1D. Los resultados se devuelven para visualización (osciloscopio, dyno, tablas de análisis) y síntesis de audio.

```
[GUI PySide6]
   └─ Árbol de proyecto y panel de propiedades
        └─ Actualiza objetos Engine/Block/Head/... (JSON-serializables)
             └─ Solvers físicos
                 ├─ core/thermo.py  (0D ciclo Otto, VE, fricción, knock)
                 ├─ core/simulator.py (1D ondas en tubos con Lax–Wendroff)
                 └─ core/numerics.py  (kernels Numba: flujos Euler, Lax–Wendroff)
                      └─ Resultados → GUI: gráficas dyno/scope/tablas + audio .wav
```

Patrón: la GUI actúa como controlador/visór; el modelo Engine es el “M”, y los módulos `thermo.py`/`simulator.py` son el “Modelo físico” invocado por acciones de usuario (botones Dyno/Scope/Optimizer). El audio_generator produce WAV a partir de las presiones simuladas.

## 2. Diccionario de Módulos

### main.py
- **Responsabilidad:** Punto de entrada Qt; crea QApplication y `MainWindow`.
- **Claves:** `main()`.
- **Entradas/Salidas:** Inicia el loop de eventos; no recibe parámetros externos.

### core/engine_components.py
- **Responsabilidad:** Dataclasses del motor (Block, CylinderHead, Camshaft, Intake/Exhaust, Supercharger, Friction, Fuel, Engine, SimulationSettings) con `to_dict`/`from_dict` para JSON y utilidades como `displacement_cc` y `calculate_geometric_cr`.
- **Claves:** `Engine.from_dict`, `Engine.save_to_file`, `Camshaft.get_lift`, `Block.displacement_cc`, `Engine.calculate_geometric_cr`.
- **Entradas/Salidas:** Configuración estructurada del motor ↔ JSON; cálculo de desplazamiento y CR.

### core/thermo.py
- **Responsabilidad:** Simulador termodinámico 0D del ciclo Otto con eficiencia por cámara, VE (Mach, runner/exhaust tuning, restricciones de flujo), combustión Wiebe, knock y pérdidas por fricción/accesorios.
- **Claves:** `piston_geometry`, `wiebe_function`, `CylinderSimulator.run_cycle`, (y `run_pro_cycle` si se emplea en el modo avanzado).
- **Entradas/Salidas:** Recibe `Engine` y rpm; devuelve trazas de presión/volumen/par y métricas agregadas (torque, potencia, BMEP, VE, airflow, knock).

### core/simulator.py
- **Responsabilidad:** Envoltura del solver 1D para tubos de admisión/escape; construye malla, aplica BCs de válvula/fantasma y avanza con Lax–Wendroff.
- **Claves:** `PipeSolver.apply_boundary_conditions`, `PipeSolver.get_time_step`, `PipeSolver.step`.
- **Entradas/Salidas:** Recibe `Pipe` y estado de válvula/presión cilindro; produce evolución `U[:,rho, rho*u, rho*E]` en el tubo.

### core/numerics.py
- **Responsabilidad:** Kernels Numba para Euler 1D (flujos, fuentes) y Lax–Wendroff, más flujo isentrópico de válvula.
- **Claves:** `flux_vector`, `source_terms`, `lax_wendroff_step`, `calculate_mass_flow_rate`.
- **Entradas/Salidas:** Vectores conservados ↔ flujos/estados intermedios; mdot isentrópico.

### acoustics/audio_generator.py
- **Responsabilidad:** Re-muestreo de presión en el tiempo a 44.1 kHz, filtrado y guardado WAV.
- **Claves:** `AudioSynthesizer.add_sample`, `AudioSynthesizer.process_and_save`.

### gui/main_window.py
- **Responsabilidad:** Shell Qt: árbol de proyecto, panel de propiedades dinámico, tabs de Overview/Dyno/Analysis/Optimizer/Scope, controles de simulación, optimizador de parámetros, HUD, navegación rápida.
- **Claves:** `refresh_tree`, `update_properties_panel`, `run_dyno_sweep`, `run_pro_dyno_sweep`, `run_optimization_sweep`, `update_overview`.
- **Entradas/Salidas:** Interactúa con Engine y solvers; presenta gráficas (pyqtgraph), tablas, audio y resumen HTML.

### tests/*
- **Responsabilidad:** Cobertura unitaria e integración (identidades HP↔Torque, tendencias de tuning, bandas de sanidad por BMEP/VE, regresiones K20/V8/V10/Eco). Incluye `pytest.ini` y seeds deterministas.

## 3. Lógica Crítica y Algoritmos

### Ghost Cells en el solver 1D (`core/simulator.py` + `core/numerics.py`)
- El tubo se discretiza en celdas y se integra con Lax–Wendroff (`lax_wendroff_step`).
- **Inlet (válvula abierta):** la celda 0 se fuerza con estado ideal-gas consistente con `p_cyl`/`T_cyl`; se "empuja" la celda 1 para iniciar la onda.
- **Inlet (válvula cerrada):** celda fantasma reflectiva: copia densidad/energía de la celda 1 e invierte el momento para `u≈0`, evitando presión atrapada.
- **Outlet:** copia transmisiva (`U[-1]=U[-2]`) para minimizar reflexiones.
- **CFL:** `get_time_step` usa velocidad de onda máxima |u|+a para dt estable; se recalcula tras aplicar BCs.

### Ciclo de 4 tiempos y máscaras en `CylinderSimulator.run_cycle`
- Se generan ángulos 0–720° en pasos de 0.5°.
- Eventos de leva (IVC/EVO) se calculan desde LSA/advance y se recortan a ventanas físicas: admisión `<IVC`, compresión `[IVC,360)`, potencia `[360,EVO)`, escape `>=EVO`.
- Mascaras booleanas evitan solapes vacíos y garantizan compresión antes de combustión, previniendo par negativo.
- Compresión/expansión adiabática: `P*V^γ=C` con volumen real en IVC; combustión Wiebe añade ΔP en potencia.

### Modelo de Fricción y Bombeo (`thermo.py`)
- FMEP tipo Chen–Flynn ajustado por tipo de bottom-end (Standard/Performance/Race) y pérdidas de accesorios (bomba agua, alternador, dirección, ventilador).
- El par de fricción se resta del indicado y se limita a no producir potencias negativas.

### Restricciones de Flujo y VE
- VE combina: Mach Index (área de válvula vs pistón y velocidad media del pistón), tuning acústico de admisión (Helmholtz/harmónicos de runner), tuning de escape y restricciones por caudal de puerto/tb total (escalado por nº de cilindros).
- Aire atrapado usa volumen en IVC y P_manifold (incluye boost). Knock reduce potencia si la CR dinámica supera la octana disponible.

### Audio y Dyno
- Audio: interpolación a 44.1 kHz con filtro pasa-altas y normalización antes de exportar WAV.
- Dyno/Pro Dyno: `run_cycle` (rápido, tablas calibradas) y `run_pro_cycle` (más geométrico) se grafican; Analysis Data tab muestra métricas por RPM y resalta máximos.

## 4. Guía de Mantenimiento y Debugging

- **NaNs/Explosiones en 1D:** Revisar clamps en `PipeSolver.step` y dt (CFL). Verificar BCs (valve_area>0 fuerza estado ideal) y asegurar longitudes SI.
- **Línea plana en Scope:** Confirmar que `apply_boundary_conditions` se ejecuta antes del cálculo de dt y que `self.U[-1]=self.U[-2]` permite salida. Revisar amplitud de señal de entrada (p_cyl/valve_area).
- **Potencia negativa/baja en 0D:** Verificar IVC/EVO y CR dinámica; chequear `chamber_design` y fuel (octanaje/energía); inspeccionar fricción y restricciones de flujo (CFM válvulas/tb).
- **Constantes físicas:** `GAMMA`, `R_AIR`, `LHV_DEFAULT`, `AFR_STOICH`, `P_ATM`, `T_INTAKE` en `core/thermo.py`; `GAMMA`, `R` en `core/numerics.py`.
- **Pruebas:** Ejecutar `pytest -q` para identidades rápidas; `pytest -q -m integration` requiere NumPy y valida tendencias/bandas de sanidad multi-motor.

## 5. Roadmap / Deuda Técnica

- Acoplar 0D↔1D en tiempo real (cilindro ↔ red de tubos) en ambos sentidos de flujo.
- Mejorar el modelo de audio (interpolación adaptativa y HRTF opcional).
- Extender optimizador para incluir restricciones de knock/temperatura de gases.
- Añadir control de RNG/semilla interno en solvers si se introduce ruido estocástico.
- Sustituir prints de debug por `logging` configurado y añadir perfiles de rendimiento numérico.
