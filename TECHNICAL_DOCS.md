# PyWaveDyn — Especificación Técnica v3.1

## 1. Constantes Físicas y Unidades (Axiomas)
- **Ecuación de estado (EoS) gas ideal**: \(U=[\rho,\rho u,\rho E]\), con velocidad \(u = U[1]/U[0]\), y presión \(p = (\gamma - 1)\big(U[2] - 0.5\,U[1]^2/U[0]\big)\) usando densidad de energía (no energía específica).
- **Constantes**: \(\gamma\) (configurable: aire 1.40, gases de escape 1.35), \(R = 287.0\,\text{J/(kg·K)}\).
- **Presiones absolutas** en Pa. Manifold absoluto: \(P_{manifold} = (P_{amb,bar} + P_{boost,gauge,bar})\times 100{,}000\).
- **RPM** siempre en rev/min para todas las ecuaciones (FMEP, velocidad media de pistón, etc.).
- **FMEP (kPa)**: \(FMEP_{kPa} = A + B\,RPM + C\,RPM^2\) con \(A\) [kPa], \(B\) [kPa/RPM], \(C\) [kPa/RPM\(^2\)]. Par de fricción 4T: \(T_{fric}[Nm] = \tfrac{FMEP_{Pa}\,V_{disp,m3}}{4\pi}\).
- **Índice de Mach**: \(c_{sound} = \sqrt{\gamma R T_{intake}}\); la temperatura de referencia proviene de `SimulationSettings.air_temperature_c`.
- **Dominio angular 0–720° CA** para cada ciclo: 0° TDC solape, 180° BDC fin admisión / inicio compresión, 360° TDC compresión, 540° BDC expansión, 720° TDC inicio nuevo ciclo.

## 2. Modelo 0D – Termodinámica (core/thermo.py)
- **Desacoplo del 1D**: el solver 0D calcula par/potencia sin retroalimentación del solver 1D. El escape se modela con una contrapresión heurística \(P_{exh} = P_{amb}\cdot exhaust\_backpressure\_factor\) (default 1.05).
- **Fases del ciclo (máscaras)**:
  - Admisión: 0°–IVC (cierre admisión).
  - Compresión: IVC–360°.
  - Potencia: 360°–EVO (combustión inicia en \(360° - advance\)).
  - Escape: ≥EVO hasta 720° usando \(P_{exh}\) definido arriba (\(P_{amb}\cdot exhaust\_backpressure\_factor\)).
- **Masa atrapada**: \(m_{air} = VE \cdot \tfrac{P_{manifold}\,V_{IVC}}{R\,T_{charge}}\), usando volumen real en IVC.
- **Combustión (Wiebe)**: \(x(\theta)=1-\exp\{-a\big(\tfrac{\theta-\theta_{start}}{\Delta\theta}\big)^{m+1}\}\) con \(a,m\) tomados de `Combustion.wiebe_a/m`. Calor químico \(Q_{chem} = m_{fuel}\,LHV\); eficiencia de combustión \(\eta_{comb}\) aplicada antes de pérdidas térmicas.
- **Transferencia de calor (Woschni)**: coeficiente \(h_c = k_{w}\,B^{-0.2} P^{0.8} T^{-0.55} w^{0.8}\) escalado por `heat_loss_factor`; \(w\approx2.28\)·velocidad media de pistón. Pérdida: \(Q_{loss} = h_c A_{wall}(T_{gas}-T_{wall})\,dt\); \(T_{wall}\) ≈ 450 K. Para cilindros pequeños se escala con el factor de calibre documentado en el código (raíz de \(85/B\)).
- **Energía neta**: \(dQ_{net} = \eta_{comb}\,dQ_{Wiebe} - dQ_{loss}\). \(U_{int}\) es la energía interna total del gas atrapado [J]; \(m\) es la masa atrapada usada en el cierre (constante en el ciclo 0D si no hay intercambio de masa).
  - Actualización 0D: \(U_{int} \leftarrow U_{int} + dQ_{net}\).
  - Cierre termodinámico (gas ideal): \(T \leftarrow U_{int}/(m c_v)\) con \(c_v = R/(\gamma-1)\); \(p \leftarrow m R T / V\). \(\gamma\) y \(R\) se definen en la Sección 1.
- **VE dinámica**: curva anclada en `Camshaft.peak_rpm`; penalización por Mach usando `Head.mach_tolerance`; área efectiva escalada por `Head.port_flow_efficiency`; pérdidas por tubería con `SimulationSettings.pipe_friction_factor`; resonancia modulada por `SimulationSettings.tuning_sensitivity`.
- **Fricción y accesorios**: FMEP con coeficientes en `Friction` y multiplicador `global_scaling_factor`; se suma torque de accesorios para obtener par de fricción total. Par efectivo = Par indicado − Par fricción − pérdidas de bombeo con `pumping_loss_torque_nm = 0` por defecto (no se descuenta bombeo adicional en el 0D).
- **Knock**: calcula octanaje requerido a partir de compresión dinámica; si supera el octanaje disponible, activa `knock_warning` pero no modifica el solver 1D.

## 3. Modelo 1D – Dinámica de Gases (core/numerics.py, core/simulator.py, core/junctions.py)
- **Ecuaciones**: Euler 1D inviscid con términos fuente (Darcy–Weisbach): \(S_{mom} = -\tfrac{f}{2D}\,\rho u|u|\), \(S_E = u\,S_{mom}\); sin transferencia de calor (adiabático).
- **Estado y flujo**: \(U=[\rho,\rho u,\rho E]\); \(F=[\rho u, \rho u^2 + p, (\rho E + p)u]\) con \(p\) según EoS anterior.
- **Esquema**: Lax–Wendroff con celdas fantasma; CFL elige \(dt\); las fronteras se reimponen tras cada paso para preservar BC.
- **Condiciones de frontera explícitas**:
  - **Inlet con válvula (isentrópico)**: se calcula flujo másico/entalpía vía tobera isentrópica usando \(P_{stag}, T_{stag}\) del cilindro/puerto (condiciones de estancamiento entregadas por el solver 0D) y \(P_{static}\) de la celda 0. Criterio: si \(P_{static}/P_{stag} \le P_{crit}\) con \(P_{crit} = (\tfrac{2}{\gamma+1})^{\gamma/(\gamma-1)}\) → flujo ahogado; los términos de masa/energía se inyectan en la celda 0. En el modelo actual 0D no se resuelve velocidad de puerto (\(u_{port}=0\)), por lo que \(P_{stag}=P_{cyl}\) y \(T_{stag}=T_{cyl}\) (totales = estáticos en el upstream 0D).
  - **Inlet cerrado**: celda fantasma reflectiva \(\rho_0=\rho_1\), \((\rho u)_0 = - (\rho u)_1\), \((\rho E)_0 = (\rho E)_1\).
  - **Outlet abierto**: presión estática fija \(P_{amb}\) en la celda fantasma; convención \(u>0\) indica salida. Si \(u_{internal}>0\) (outflow) \(T_{ghost}=T_{internal}\); si \(u_{internal}<0\) (inflow) \(T_{ghost}=T_{amb}\) con \(T_{amb}=air\_temperature\_c+273.15\). Se construye \(U_{ghost}=[\rho_{ghost},\rho_{ghost}u_{ghost},p_{ghost}/(\gamma-1)+0.5\,\rho_{ghost}u_{ghost}^2]\) usando \(p_{ghost}=P_{amb}\), \(u_{ghost}=u_{internal}\) (gradiente cero) y \(\rho_{ghost}=p_{ghost}/(R\,T_{ghost})\). No se usa condición transmisiva sin presión fija para preservar reflexiones.
- **Junctions**: \(\tfrac{dm}{dt} = \sum \dot m\), \(\tfrac{d(me)}{dt} = \sum (\dot m h_{tot})\); actualización de \(p,T\) mediante EoS en volumen constante.
- **Red de escape**: `Engine1DSolver` construye primarios (uno por cilindro), colector 0D y tailpipe; fasea eventos con firing order; se usa sólo para Scope/Acústica (acoplamiento unidireccional desde presión 0D).

## 4. Arquitectura y Flujo de Datos
1. **Entrada GUI (PySide6/pyqtgraph)** edita el modelo (`core/engine_components.py`) y lanza simulaciones.
2. **Persistencia**: JSON ↔ dataclasses (`Engine.from_dict/to_dict`); presets en la raíz (K20, V8, F1, kart, etc.).
3. **Ciclo 0D (core/thermo.py)**: calcula par/potencia/VE/knock usando backpressure heurística; alimenta Dyno, Analysis, Optimizer.
4. **Onda 1D (core/simulator.py + core/numerics.py + core/junctions.py)**: consume perfiles de presión 0D o impulsos sintéticos como BC de válvula para visualización y síntesis de audio; no retroalimenta al 0D.
5. **Acústica (acoustics/audio_generator.py)**: remuestrea presión de salida 1D y mezcla por firing order para generar WAV.

## 5. Contrato de Verificación
- **Determinismo lógico**: misma entrada y semilla → resultados iguales dentro de tolerancia \(10^{-5}\), aceptando variaciones FP entre CPUs/BLAS.
- **Identidades físicas**: Potencia-torque: \(P_{kW} = T_{Nm}\,RPM/9549\), \(P_{hp} = T_{Nm}\,RPM/7127\) (hp mecánico, convención usada en `mean_power_hp`); BMEP↔Torque (4T: \(BMEP_{Pa} = 4\pi T/V_{disp}\), \(BMEP_{bar} = BMEP_{Pa}/100{,}000\) cuando se expresa en bar). FMEP usa RPM en rev/min y presiones absolutas.
- **Bandas de sanidad**: aplican a configuraciones estándar (combustible común, aire estándar). Mezclas exóticas o geometrías fuera de rango requieren recalibración y no están cubiertas por las pruebas de regresión.
- **Separación funcional**: el 0D es autónomo; el 1D sólo consume BC explícitas. Cualquier acoplamiento bidireccional nuevo debe especificarse y probarse por separado.
