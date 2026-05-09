"""Implemets a non-decomposed baseline."""

import gurobipy as gp

from .config import CONSTANTS
from .io_utils.translator import ORIGIN

DEFMAX = CONSTANTS["max_dev"]


class CentralSolver:
    """A wrapper for Gurobi solver."""

    def __init__(
        self,
        boundcls: tuple,
        dbound=DEFMAX,
        amb_risks: dict = {},
    ):
        """Initializes a centralized solver.

        Args:
            boundcls (tuple): Holds bounds of precendence relations.
            dbound : Maximum deviation.
            amb_risks: Specifies wether some variable should be either 0 or not 0.
        """
        self.d_max = dbound
        self.sv = gp.Model("central_solver")
        self.sv.setParam("OutputFlag", False)
        self.sv.setParam("Presolve", 2)
        # Initialize variable sets for segment times and deviations
        ts = {}
        ds = {}
        # Add constraints
        for bd in boundcls:
            # Match the key type to know which relations bd refers to
            match next(iter(bd)):
                case ((_, _), (_, _)):
                    self.add_fixed(bd, ts)
                case (_, _):
                    self.add_deviations(bd, ts, ds)
                case _:
                    self.add_selectables(bd, ts)
        self.ts = ts
        self.ds = ds
        for t, ps in amb_risks.items():
            self._ensure_unambiguity(t, ps)

        # Set the objective function
        self.sv.setObjective(gp.quicksum(d for d in ds.values()), sense=gp.GRB.MINIMIZE)
        # Store time and deviations variables for accessing them later

    def _ensure_unambiguity(self, train, stations):
        for s in stations:
            cs = self.sv.addVars(s, vtype=gp.GRB.BINARY)
            self.sv.addConstr(gp.quicksum(cs) == len(s) - 1)
            for p in s:
                self.sv.addGenConstrIndicator(cs[p], True, self.ts[(train, p)] == 0)

    def add_fixed(self, dat: dict, tvars: dict):
        """Add constraints for fixed precedence relations.

        Args:
            dat (dict): The relation bounds.
            tvars (dict): The time variables.
        """
        for i, j in dat:
            self.add_dictVar(tvars, i, "t")
            self.add_dictVar(tvars, j, "t")
            self.sv.addConstr(tvars[j] - tvars[i] >= dat[i, j])

    def add_selectables(self, dat: dict, tvars: dict):
        """Add constraints for selectable precedence relations.

        Args:
            dat (dict): The relation bounds.
            tvars (dict): The time variables.
        """
        for d in dat:
            # Add auxiliary variables which describe wether a choice is made or not.
            cs = self.sv.addVars(dat[d], vtype=gp.GRB.BINARY)
            # Make sure only one choice is made per decision.
            self.sv.addConstr(gp.quicksum(cs) == 1)
            # Add constraints indicated by an auxiliary variable.
            for c in dat[d]:
                for i, j in dat[d][c]:
                    self.add_dictVar(tvars, i, "t")
                    self.add_dictVar(tvars, j, "t")
                    self.sv.addGenConstrIndicator(
                        cs[c], True, tvars[j] - tvars[i] >= dat[d][c][i, j]
                    )

    def add_deviations(self, dat: dict, tvars: dict, dvars: dict):
        """Add deviation constraints.

        Args:
            dat (dict): The deviation bounds.
            tvars (dict): The time variables.
            dvars (dict): The deviation variables.
        """
        for i in dat:
            self.add_dictVar(tvars, i, "t")
            dvars[i] = self.sv.addVar(name=f"d_{i}", ub=self.d_max)
            self.sv.addConstr(dvars[i] - tvars[i] >= -1 * dat[i])

    def add_dictVar(self, d: dict, idx, n: str):
        """Adds a variable if not already existing.

        Args:
            d (dict): Where the variable is stored.
            idx (Any): Index of the variable.
            n (str): Name of the variable.
        """
        if idx not in d.keys():
            var = self.sv.addVar(name=f"{n}_{idx}")
            d[idx] = var
            if idx == ORIGIN:
                self.sv.addConstr(d[idx] == 0)

    def solve(self):
        self.sv.optimize()
        if self.sv.Status != gp.GRB.OPTIMAL:
            print("Problem was not feasible!")
            return {}, float("inf")
        else:
            # print("\nSolution", "\n=====================================")
            # for t in self.ts:
            #     print(t, " -- ", self.ts[t])
            # print("Total deviation: ", sum(d.X for d in self.ds.values()))
            # print("=====================================\n")
            solution = {}
            for (x, y), var in self.ts.items():
                if x > 0 and y >= 0:
                    solution.update({(x, y): var.X})
            total = sum(d.X for d in self.ds.values())
            self.sv.close()
            return solution, total
