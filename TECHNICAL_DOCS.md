# PyWaveDyn — Especificación Técnica v3.0

## Convenciones y Unidades (Axiomas)
- **Dominio angular 0–720° CA** para un ciclo de 4 tiempos: 0° TDC solape, 180° BDC admisión/escape, 360° TDC compresión/combustión, 540° BDC expansión.
- **Presiones absolutas** en Pa salvo que se indique lo contrario. Manifold: \(P_{manifold,abs} = (P_{ambient,bar} + P_{boost,gauge,bar}) \times 100{,}000\).
- **RPM** siempre en rev/min; no se usan rad/s en las ecuaciones de FMEP.
- **FMEP (kPa)**: \(FMEP_{kPa} = A + B\cdot RPM + C\cdot RPM^2\). Par de fricción 4T: \(T_{fric}[Nm] = \frac{FMEP_{Pa} \cdot V_{disp,m3}}{4\pi}\).
- **Índice de Mach**: \(c_{sound} = \sqrt{\gamma R T_{intake}}\); se usa \(T_{intake}\) del entorno para calcular velocidades críticas.
- **Estado 1D**: \(U = [\rho, \rho u, \rho E]\) con \(p = (\gamma-1)(E - 0.5\,\rho u^2)\).
- **Determinismo lógico**: mismas entradas y semilla ⇒ resultados iguales dentro de tolerancia flotante \(10^{-5}\) considerando variaciones de plataforma.

## Modelo 0D – Termodinámica (core/thermo.py)
- **Independencia del 1D**: el ciclo 0D se ejecuta aislado; el escape usa una contrapresión heurística \(P_{atm}\times1.05\). No hay realimentación del solver 1D; el 1D solo consume históricos de presión 0D para visualización/acústica (acoplamiento unidireccional).
- **Fases (máscaras angulares)**:
  - Admisión: 0°–IVC.
  - Compresión: IVC–360°.
  - Potencia: 360°–EVO (inicio de combustión = 360° – \(advance\)).
  - Escape: ≥EVO hasta 720° con presión de referencia \(1.05\,P_{atm}\).
- **Masa atrapada**: \(m_{air} = VE \cdot \frac{P_{manifold,abs} \cdot V_{IVC}}{R T_{charge}}\), usando el volumen real a IVC.
- **Combustión (Wiebe)**: \(x(\theta) = 1-\exp(-a ((\theta-\theta_{start})/\Delta\theta)^{m+1})\); parámetros \(a,m\) vienen de `Combustion`. Calor liberado usa LHV del combustible y \(Q_{chem}=Q_{total}\cdot\eta_{combustion}\).
- **Pérdida de calor (Woschni)**: coeficiente \(h_c = 3.26\,B^{-0.2} P^{0.8} T^{-0.55} w^{0.8}\) escalado por `heat_loss_factor`; \(w\approx2.28\)·velocidad media de pistón. Flujo: \(Q_{loss} = h_c A_{wall}(T_{gas}-T_{wall})\,dt\).
- **Energía neta**: \(dQ_{net} = dQ_{Wiebe} - dQ_{loss}\); presión de potencia \(p = p_{adiab} + (\gamma-1) dQ_{net}/V\).
- **VE dinámica**: curva basada en `peak_rpm` y duración de levas; penalización por índice de Mach con tolerancia de la culata y eficiencia de flujo; pérdidas de tubería escaladas por `pipe_friction_factor`; resonancia escalada por `tuning_sensitivity`.
- **Fricción**: aplica FMEP con coeficientes del motor y multiplicador `global_scaling_factor`; torque de bombeo/accesorios se suma al par de fricción para obtener par efectivo.
- **Knock**: compara compresión dinámica y octanaje; activa `knock_warning` pero no altera el solver 1D.

## Modelo 1D – Dinámica de Gases (core/numerics.py, core/simulator.py, core/junctions.py)
- **Ecuaciones**: Euler 1D inviscido, compresible, con fuente de fricción Darcy–Weisbach \(S_{fric} = -\frac{f}{2D}\,\rho u|u|\) aplicada a momento y energía; sin transferencia de calor (adiabático).
- **Estado y flujo**: \(U=[\rho,\rho u,\rho E]\); flujo \(F=[\rho u, \rho u^2 + p, (\rho E + p)u]\) con \(p\) según EoS.
- **Esquema numérico**: Lax–Wendroff con celdas fantasma. CFL controla \(dt\); se restaura frontera tras cada paso para conservar BC impuestas.
- **Condiciones de frontera**:
  - Inlet cerrado: celda fantasma reflectiva \(\rho_0=\rho_1, (\rho u)_0=-(\rho u)_1, (\rho E)_0=(\rho E)_1\).
  - Inlet con válvula: acople isentrópico (nozzle) para calcular \(\dot m\) y actualizar celda 0.
  - Outlet: transmisiva \(U_N = U_{N-1}\), manteniendo \(p_{static}=P_{amb}\) en subsónico.
- **Junctions**: conservan masa \(\frac{dm}{dt} = \sum \dot m\) y energía \(\frac{d(me)}{dt} = \sum (\dot m h_{tot})\); actualización de \(p,T\) via gas ideal en volumen fijo.
- **Red de escape**: `Engine1DSolver` construye primarios (uno por cilindro), unión colectora y tailpipe; fasea blowdown con firing order; se usa para Scope/Audio, no para el cálculo de par 0D.

## Arquitectura de Software (Flujo de Datos)
1. **GUI (PySide6/pyqtgraph)** edita el modelo (`core/engine_components.py`) y lanza simulaciones.
2. **Ciclo 0D (core/thermo.py)**: calcula par/potencia, VE, knock; usa sólo contrapresión heurística. Resultados alimentan Dyno/Optimizer/Analysis.
3. **Onda 1D (core/simulator.py + core/numerics.py + core/junctions.py)**: consume historia de presión 0D o perfiles sintéticos como BC de válvula para visualizar/acoplar audio; no retroalimenta al 0D.
4. **Acústica (acoustics/audio_generator.py)**: re-muestrea presión de salida 1D y mezcla por orden de encendido.
5. **Persistencia**: JSON <-> dataclasses; presets en raíz.

## Contrato de Pruebas y Verificación
- **Determinismo lógico**: mismo input y semilla ⇒ resultados iguales dentro de \(10^{-5}\); aceptar variaciones menores por FP entre CPUs/NumPy.
- **Bandas de sanidad**: aplican a configuraciones estándar (aire seco, combustibles comunes, ajustes de fábrica de pruebas). No garantizan para mezclas exoticas o geometrías fuera de rango.
- **Identidades físicas**: Consistencia HP↔Torque (HP = T·RPM/9549), BMEP↔Torque (para 4T: BMEP = 4πT/Vdisp). Fricción y Mach usan unidades definidas arriba.
- **Separación de responsabilidades**: el 0D no depende del 1D; el 1D sólo debe consumir BCs explícitas. Cualquier acoplamiento bidireccional debe ser tratado como nueva característica y documentarse.
