"""A Trainrouting Algorithm based on a combinatorial Benders decomposition."""

import os
import pickle
import time

from .centralized import CentralSolver
from .config import CONSTANTS
from .experiments.data import Result
from .io_utils.translator import constraints_from_file, total_dev
from .satsolving.z3wrapper import EmptyCoreExecption
from .satsolving.z3wrapper import SatProblem as SAT
from .setcovering.qasmrun import TQUEUE, init_service
from .setcovering.qasmsolver import QUBITCOUNT
from .setcovering.scpwrapper import Problem as SetCoverProblem

DISCRET = CONSTANTS["discrets"]
MAXDEV = CONSTANTS["max_dev"]


def get_qcount():
    try:
        with open(QUBITCOUNT, "rb") as f:
            c = pickle.load(f)
            print(c)
        os.remove(QUBITCOUNT)
        print(c)
        return c if c else [0]
    except (EOFError, FileNotFoundError):
        return [0]


def get_queuetime():
    try:
        with open(TQUEUE, "rb") as f:
            t = pickle.load(f)
        os.remove(TQUEUE)
        return t
    except (EOFError, FileNotFoundError):
        return 0


def route():
    """Implements routing workflow.

    Returns:
        UndefinedType: times formatted in a timetable
    """
    constraints = constraints_from_file()
    times = benders_algorithm(constraints)
    return times


def benders_algorithm(constr, platforms, scp_strat="greedy", **kwargs) -> Result:
    """Implements a combinatorial benders decomposition.

    Returns:
        Result: Computation result including solution and measurements.
    """
    if scp_strat == "quantum" and kwargs:
        init_service()
    start_time = time.time()
    # Instantiate Problems.
    master = SetCoverProblem()
    sub = SAT(*constr, d_max=MAXDEV, k=DISCRET, amb_risks=platforms)
    selection = []
    itercount = 0
    while True:
        # Remove some constraints from sub according to the Master's solution.
        try:
            sat, model, infeasibles = sub.solve(disabled_from=selection)
        except EmptyCoreExecption:
            execution_time = time.time() - start_time
            print("Problem was infeasible with given maximal deviation.")
            print(f"Exited after {itercount} iterations.")
            qcnts = get_qcount()
            return Result(
                time=execution_time,
                iter_num=itercount,
                total_dev=float("inf"),
                max_qubits=qcnts[-1],
                qubit_cnts=qcnts,
            )
        if sat:
            execution_time = time.time() - start_time
            # Return a model of the set of constraints as solution.
            qcnts = get_qcount()
            execution_time -= get_queuetime()
            return Result(
                model=model,
                time=execution_time,
                iter_num=itercount,
                total_dev=total_dev(constr, model),
                max_qubits=qcnts[-1],
                qubit_cnts=qcnts,
            )
        else:
            # Add a cut for the master problem from an infeasible subset of sub's constraints.
            master.add(infeasibles)
            # Select constraints to skip in the next iteration.
            selection = master.solve(strategy=scp_strat, **kwargs)
        itercount += 1


def central_algorithm(constr, platforms):
    """Wraps a CentralSolver object used to solve the problem.

    Returns:
        Result: Computation result including solution and measurements."""
    start_time = time.time()
    Solver = CentralSolver(constr, amb_risks=platforms)
    model, total = Solver.solve()
    execution_time = time.time() - start_time
    return Result(model=model, time=execution_time, total_dev=total)


if __name__ == "__main__":
    route()
