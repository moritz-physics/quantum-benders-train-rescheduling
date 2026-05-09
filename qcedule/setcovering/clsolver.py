"""Wraps classical solvers for SCP to support DataFrames as problem representation."""

from typing import Any

import gurobipy as gp
import pandas as pd
import SetCoverPy.setcover as sc


def greedy_solve(data: pd.DataFrame, **kwargs) -> set[Any]:
    """A wrapper for the greedy algorithm.

    Args:
        data (pd.DataFrame): Represents the problem instance.

    Returns:
        set[Any]: The labels of selected subsets.
    """
    if data.empty:
        return {}
    # Set equal cost for each subset
    cost = [1 for _ in data.columns]
    # Initialize solver and solve
    solver = sc.SetCover(data, cost)
    solver.greedy()
    # Get labels of the subsets that were selected
    labels = {x for t, x in zip(solver.s, data.columns) if t}
    return labels


def gurobi_solve(data: pd.DataFrame, **kwargs) -> set[Any]:
    """ "A wrapper for gurobi solver.

    Args:
        data (pd.DataFrame): Represents the problem instance.

    Returns:
        set[Any]: The labels of selected subsets.
    """

    # Build linear problem based on the data
    solver = gp.Model("solver")
    solver.setParam("OutputFlag", 0)
    xs = solver.addVars(data.columns, vtype=gp.GRB.BINARY, name="x")
    solver.addConstrs(
        gp.quicksum(xs[i] for i in data.columns if data.at[j, i]) >= 1
        for j in data.index
    )
    solver.setObjective(gp.quicksum(xs), gp.GRB.MINIMIZE)
    # Optimize
    solver.optimize()
    # Get labels of variables that are 1 after optimizing
    labels = {i for i in data.columns if xs[i].X}
    return labels
