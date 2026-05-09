import unittest

import numpy as np
import pandas as pd

from qcedule.setcovering.scpwrapper import SOLVERS, Problem

# Generate a Probolem
superset = set(range(14))
a = {i for i in superset if i % 2}
b = {i for i in superset if not i % 2}
c = {0, 7}
d = {1, 2, 8, 9}
e = {3, 4, 5, 6, 10, 11, 12, 13}
a_, b_, c_, d_, e_ = "a", "b", "c", "d", "e"
subsetlabels = [a_, b_, c_, d_, e_]
subsets = [a, b, c, d, e]
matrix = np.matrix([[i in j for j in subsets] for i in superset])
data = pd.DataFrame(matrix, columns=subsetlabels)


class TestSetCovering(unittest.TestCase):
    prob = Problem(data)

    def test_init(self):
        """Test if Problem constructor works."""
        emptyp = Problem()
        self.assertTrue(emptyp.matrix.empty)

    def test_solvers(self):
        """Test the solvers."""
        s_gr = SOLVERS["greedy"](self.prob.matrix)
        s_gu = SOLVERS["gurobi"](self.prob.matrix)
        # greedy can't solve it optimally
        self.assertEqual(s_gr, {d_, c_, e_})
        # gurobi will find an optimal solution
        self.assertEqual(s_gu, {a_, b_})

    def test_add(self):
        """Test if add does its job."""
        new = Problem()
        # Build same Problem as "prob" but with Problem.add()
        for i in superset:
            containers = [k for k, j in zip(subsetlabels, subsets) if i in j]
            new.add(containers)
        # Check equality
        pd.testing.assert_frame_equal(new.matrix, self.prob.matrix, check_like=True)
        # Check if adding empty list is ok

    def test_solve(self):
        # Check empty problem
        self.assertEqual(Problem().solve(), {})

        greedy = self.prob.solve("greedy")
        gurobi = self.prob.solve("gurobi")
        test = self.prob.solve("invalid")
        # greedy can't solve it optimally
        self.assertEqual(greedy, {d_, c_, e_})
        # gurobi will find an optimal solution
        self.assertEqual(gurobi, {a_, b_})
        # check if invalid solver gets handled by using greedy per default
        self.assertEqual(greedy, test)
        # Check if uncovered row gets handled with an AssertionError
        mat = self.prob.matrix.copy()
        new = Problem(mat)
        new.add([])
        self.assertRaises(AssertionError, new.solve)


if __name__ == "__main__":
    unittest.main()
