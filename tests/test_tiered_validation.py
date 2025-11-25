import pytest
import numpy as np
import math
from core.engine_components import Engine
from core.thermo import CylinderSimulator, piston_geometry

# --- CONFIGURACIÓN BASE ACTUALIZADA (Honda K20A 2.0L) ---
# Adaptada al nuevo esquema de engine_components.py
K20_DATA = {
    "block": {
        "bore": 86.0, 
        "stroke": 86.0, 
        "conrod_length": 139.0, 
        "num_cylinders": 4,
        "redline_rpm": 8500.0
    },
    "head": {
        "compression_ratio": 11.5, 
        "intake_valves": 2, 
        "port_flow_cfm": 290.0,
        "intake_valve_diameter": 35.0,
        "exhaust_valve_diameter": 30.0
    },
    "camshaft": {  # Nombre corregido (antes era "cam")
        "intake_lift": 11.5, 
        "intake_duration": 260.0, 
        "exhaust_duration": 260.0,
        "lobe_separation": 107.0
    },
    "intake": {
        "runner_length": 230.0, 
        "runner_diameter": 48.0, 
        "throttle_cfm": 1000.0
    },
    "exhaust": {
        "header_primary_length": 450.0
    },
    "supercharger": {
        "type": "NA", 
        "boost_pressure_bar": 0.0
    },
    "simulation_settings": {
        "ignition_timing_btdc": 30.0
    }
}

@pytest.fixture
def k20_engine():
    return Engine.from_dict(K20_DATA)

# ==========================================
# NIVEL 1: DATOS Y GEOMETRÍA (¿Sabe sumar?)
# ==========================================
class TestLevel1_Basics:
    
    def test_displacement_calculation(self, k20_engine):
        """Verifica que 86x86mm x 4 cil de ~1998 cc."""
        disp = k20_engine.block.displacement_cc
        print(f"\n[N1] Desplazamiento calculado: {disp:.2f} cc")
        assert 1990.0 < disp < 2010.0

    def test_compression_ratio_integrity(self, k20_engine):
        """Verifica que la RC se guarda correctamente."""
        assert k20_engine.head.compression_ratio == 11.5

    def test_piston_movement(self):
        """Verifica matemáticas de movimiento de pistón."""
        angles = np.array([0.0, 180.0, 360.0])
        # bore, stroke, conrod en mm
        vol_swept, _ = piston_geometry(angles, 86.0, 86.0, 139.0)
        
        # En 0 (TDC) el volumen barrido es 0
        assert abs(vol_swept[0]) < 1e-9 
        # En 180 (BDC) el volumen es máximo
        assert vol_swept[1] > 0.0
        # En 360 (TDC) vuelve a 0
        assert abs(vol_swept[2]) < 1e-9

# ==========================================
# NIVEL 2: COMPONENTES (¿Funcionan las piezas?)
# ==========================================
class TestLevel2_Components:
    
    def test_cam_lift_profile(self, k20_engine):
        """Verifica que la leva abre y cierra."""
        cam = k20_engine.camshaft
        # Pico de admisión suele ser ~107 grados (LSA - Advance)
        lift_peak = cam.get_lift(107.0, intake=True) 
        lift_base = cam.get_lift(360.0, intake=True) # TDC combustión (cerrada)
        
        print(f"\n[N2] Leva: Lift Peak={lift_peak:.2f}mm, Base={lift_base:.2f}mm")
        
        assert lift_peak > 10.0 # Debe estar cerca de 11.5
        assert lift_base < 0.1  # Debe estar cerrada

# ==========================================
# NIVEL 3: CICLO COMPLETO (¿Arranca el motor?)
# ==========================================
class TestLevel3_Simulation:
    
    def test_engine_performance_k20(self, k20_engine):
        """Corre un ciclo a 7000 RPM y verifica potencia realista para un K20."""
        sim = CylinderSimulator(k20_engine)
        results = sim.run_cycle(7000.0)
        
        tq = results["mean_torque_nm"]
        hp = results["mean_power_hp"]
        bmep = results["bmep_bar"]
        ve = results["ve_percent"] if "ve_percent" in results else results["ve"]
        
        print(f"\n[N3] K20 @ 7000: {hp:.1f} HP, {tq:.1f} Nm, BMEP={bmep:.1f}, VE={ve:.1f}%")
        
        # Criterios de éxito para un K20 2.0L (Ajustados a nueva física con fricción)
        assert 180.0 < hp < 240.0, f"Potencia fuera de rango ({hp:.1f} HP). Esperado ~200-220"
        assert 190.0 < tq < 230.0, f"Torque fuera de rango ({tq:.1f} Nm). Esperado ~200-210"
        assert bmep > 10.0, "BMEP muy bajo (Motor ineficiente)"

# ==========================================
# NIVEL 4: TENDENCIAS FÍSICAS (¿Es realista?)
# ==========================================
class TestLevel4_PhysicsTrends:
    
    def test_turbo_adds_power(self, k20_engine):
        """El turbo debe dar MÁS potencia que el atmosférico."""
        # Base
        sim_na = CylinderSimulator(k20_engine)
        hp_na = sim_na.run_cycle(6000.0)["mean_power_hp"]
        
        # Turbo 1.0 Bar
        k20_engine.supercharger.type = "Turbo"
        k20_engine.supercharger.boost_pressure_bar = 1.0
        
        sim_turbo = CylinderSimulator(k20_engine)
        hp_turbo = sim_turbo.run_cycle(6000.0)["mean_power_hp"]
        
        print(f"\n[N4] Turbo: {hp_na:.1f} HP -> {hp_turbo:.1f} HP")
        
        # Debe aumentar considerablemente (>40%)
        assert hp_turbo > hp_na * 1.4

    def test_valve_restriction(self, k20_engine):
        """Válvulas pequeñas deben matar la potencia en alta."""
        # Base (35mm)
        sim_base = CylinderSimulator(k20_engine)
        hp_base = sim_base.run_cycle(8000.0)["mean_power_hp"]
        
        # Restricción (20mm)
        k20_engine.head.intake_valve_diameter = 20.0
        sim_choked = CylinderSimulator(k20_engine)
        hp_choked = sim_choked.run_cycle(8000.0)["mean_power_hp"]
        
        print(f"\n[N4] Válvulas: 35mm={hp_base:.1f} HP -> 20mm={hp_choked:.1f} HP")
        
        # Debe perder potencia
        assert hp_choked < hp_base * 0.8, "El motor no se ahogó con válvulas pequeñas"
