from qcedule.centralized import CentralSolver as Solver
from qcedule.io_utils.routes_generator import generate_linear_routes as glr


def test_short():
    t = Solver(glr(2, 2, 1000, 3000))
    t.solve()
