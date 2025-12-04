# PyWaveDyn — Visión del Proyecto

## Misión
Construir una plataforma abierta, reproducible y auditable para diseñar, simular y optimizar motores de combustión interna mediante modelos 0D/1D explícitos, con parámetros trazables y resultados justificables físicamente.

## North Star (objetivo a largo plazo)
### 1) Dyno virtual 0D (prestaciones)
- Predicción de torque/potencia basada en termodinámica 0D con combustión parametrizada y pérdidas físicas.
- Salidas: curvas de torque/potencia, VE, BSFC, balances de energía por punto de operación.

### 2) Wave Scope 1D (admisión/escape)
- Simulación 1D para visualizar propagación/reflexión de ondas en redes.
- Diagnóstico de scavenging y resonancias con mapas espacio–tiempo y métricas derivadas.

### 3) Optimización automática reproducible
- Barridos paramétricos y optimización con objetivos explícitos (pico, banda, consumo, etc.).
- Reportes con trazabilidad completa (inputs, versiones, semillas/hashes).

### 4) Acústica por síntesis física (sin samples)
- Generación de audio a partir de señales de presión simuladas.
- Mezcla multi-cilindro según orden de encendido y fase, con export y análisis espectral.

### 5) Versatilidad
- Cobertura desde monocilíndricos pequeños hasta motores multi-cilindro de alta rpm, con pérdidas relevantes.

### 6) Del bit al metal (fabricación)
- Traducción de soluciones (p. ej., escape) a cut-list/BOM y plantillas exportables.

## Estado actual (lo que el repositorio garantiza hoy)
- Dyno 0D autónomo validado por suite de pruebas.
- Solver 1D de escape disponible para Scope (contrato de integración opt-in).
- Acoplamiento 0D↔1D bidireccional: no implementado (hoy es unidireccional hacia el 1D para visualización/acústica).
- Prototipos GUI pueden existir, pero no cuentan como “implementado” sin comando/test reproducible.

## Definición de “implementado”
Una capacidad se considera implementada solo si existe un comando reproducible y/o un test verde que la cubra.
Fuente de verdad: `FEATURES.md` y `VALIDATION_GUIDE.md`.
