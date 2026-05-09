"""Implements the set cover problem as DataFrame wrapper."""

import warnings
from typing import Any, Iterable

import pandas as pd

from .clsolver import greedy_solve, gurobi_solve
from .qasmsolver import quantum_solve

SOLVERS = {"greedy": greedy_solve, "gurobi": gurobi_solve, "quantum": quantum_solve}

DEFAULT_SLV = "greedy"


class Problem:
    """A class for wrapping SCP instances."""

    def __init__(self, data=None):
        """Intitializes a Problem object."""

        self.matrix = pd.DataFrame(data)
        self.covered = True

    def solve(self, strategy: str = DEFAULT_SLV, **kwargs) -> set[Any]:
        """Solves the SCP.

        Args:
            strategy (str): Specifies the solver to be used.

        Returns:
            set[Any]: A list of labels of the selected subsets.
        """
        assert self.covered, "Not all elements can be covered and SCP is not solvable."
        # Step 1: Define a varable that is the chosen solver function from the set SOLVERS, do this by looking up in the SOLVERS library
        try:
            solver_fn = SOLVERS[strategy]
        except KeyError:
            solver_fn = SOLVERS[DEFAULT_SLV]
            warnings.warn(
                f'The solver "{strategy}" is unknown. Using greedy solver as default.'
            )
        # Step 2:  Call the defined function with the argument of the matrix, that was also given, call that result. in the add function the matrix is called self.matrix and give extra arguments **kwargs, incase the optimizer called needs extra variables.
        result = solver_fn(self.matrix, **kwargs)

        return result

    def add(self, elem: Iterable[Any]) -> None:
        """Adds elements and its containers.

        Args:
            elem (list[Any]): A list of objects acting as subset labels.
        """
        if not elem:
            self.covered = False
        # Step 1: für jedes element(label) in elem checken, ob eine Spalte existiert, wenn das nicht der Fall ist, dann für jedes neue Label eine Spalte hinzufügen und diese per default auf False setzten.
        for label in set(elem) - set(self.matrix.columns):
            self.matrix[label] = False
        # Step 2: Zeile einfügen
        self.matrix.loc[len(self.matrix)] = [
            any(i is j for j in elem) for i in self.matrix.columns
        ]
