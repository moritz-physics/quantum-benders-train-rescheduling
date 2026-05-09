from qcedule.io_utils.routes_generator import generate_linear_routes as glr
from qcedule.routing import benders_algorithm

TESTSET = glr(2, 2, 1000, 3000)


def test_framework():
    constr = TESTSET
    res = benders_algorithm(constr)
    print(res)
