"""Simple regression harness for the pipe solver."""

from core import numerics
from core.model import Pipe
from core.simulator import PipeSolver


def compute_pressure(state_row):
    rho = state_row[0]
    mom = state_row[1]
    energy = state_row[2]
    u = mom / rho
    return (numerics.GAMMA - 1.0) * (energy - 0.5 * rho * u * u)


def main():
    pipe = Pipe(length=1000.0, diameter_inlet=40.0, diameter_outlet=40.0, friction_coeff=0.01)
    solver = PipeSolver(pipe, target_dx=0.01)

    print(f"Initialized solver with N={solver.N} cells, dx={solver.dx:.6f} m")

    for i in range(50):
        dt = solver.get_time_step()
        solver.step(dt)
        if (i + 1) % 10 == 0:
            center_idx = solver.N // 2
            p_center = compute_pressure(solver.U[center_idx])
            p_exit = compute_pressure(solver.U[-1])
            print(
                f"Step {i + 1:03d} | time={solver.time:.6f}s | "
                f"p_center={p_center:.2f} Pa | p_exit={p_exit:.2f} Pa"
            )


if __name__ == "__main__":
    main()
