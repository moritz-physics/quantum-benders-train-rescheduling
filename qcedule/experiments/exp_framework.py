import datetime
import pickle
from typing import List

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import curve_fit

from ..io_utils.file_parser import (
    parse_network_file,
    parse_time,
    parse_train_file,
)
from ..io_utils.translator import build_constraints
from ..routing import benders_algorithm, central_algorithm
from .data import Result, save_results

RISKS = {
    1: [[6, 21], [33, 0], [24, 7], [27, 14], [16, 30]],
    2: [[6, 21], [33, 0], [24, 7], [27, 14], [16, 30], [17]],
    4: [[27, 14], [16, 30], [17]],
    3: [[6, 21], [33, 0], [24, 7], [27, 14], [16, 30]],
    5: [[6, 21], [33, 0], [24, 7], [27, 14], [16, 30]],
    6: [[27, 14], [24, 7], [6, 21], [33, 0]],
}
DIFFICULTY = {
    "15:32:00": 0,
    "15:33:00": 1,
    "15:34:00": 2,
    "15:35:00": 3,
    "15:36:00": 4,
    "15:37:00": 5,
    "15:38:00": 6,
    "15:39:00": 7,
    "15:40:00": 8,
    "15:41:00": 9,
    "15:42:00": 10,
    "15:43:00": 11,
    "15:44:00": 12,
    "15:45:00": 13,
    "15:46:00": 14,
    "15:47:00": 15,
    "15:48:00": 16,
    "15:49:00": 17,
    "15:50:00": 18,
}
METRICS = {
    "time": "Time",
    "iter_num": "Iterations",
    "total_dev": "Total Deviation",
    "rel_dev": "Relative Deviation",
    "max_qubits": "Maximum Qubits",
}
UNITS = {
    "time": "in s",
    "iter_num": "",
    "total_dev": "in s",
    "rel_dev": "in %",
    "max_qubits": "",
}
CONSTRPKL = "constraints.pkl"


def plot_metric(
    results: List["Result"],
    metric: str,
    ignore_method: list[str] = [],
    ignore_diff: list[int] = [],
    scatter=False,
    minmax=True,
    area=True,
):
    """
    Plot a metric across different methods and solvers.
    Includes standard deviation as shaded regions.
    """
    assert metric in {"time", "iter_num", "total_dev", "rel_dev", "max_qubits"}

    pres = [r for r in results if r.method not in ignore_method]
    # Group data by (method, solver)
    data = {}
    for r in pres:
        key = (r.method, r.solver)
        if key not in data:
            data[key] = {}
        d = DIFFICULTY[str(datetime.timedelta(seconds=r.earliest))]
        if d in ignore_diff:
            continue
        if d not in data[key]:
            data[key][d] = []
        data[key][d].append(getattr(r, metric))

    # Set style
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.figure(figsize=(10, 6))
    diffs = set()
    # Plot mean and standard deviation for each method
    for (method, _), vals in data.items():
        # Sort earliest times for consistent x-axis
        sorted_diffs = sorted(vals.items())
        x = [diff for diff, _ in sorted_diffs]  # Convert seconds to minutes
        diffs.update(x)
        y = [np.mean(vs) for _, vs in sorted_diffs]
        y_std = [np.std(vs) for _, vs in sorted_diffs]
        y_min = [min(vs) for _, vs in sorted_diffs]
        y_max = [max(vs) for _, vs in sorted_diffs]

        label = f"{method}"
        if scatter:
            popt, _ = curve_fit(lambda t, a, b: a * np.exp(b * t), x, y)
            (a, b) = popt
            y_line = [a * np.exp(b * t) for t in x]
            plt.scatter(x, y, marker="o", label=label)
            plt.plot(x, y_line)
        else:
            plt.plot(x, y, marker="o", label=label)
            if minmax:
                if area:
                    plt.fill_between(
                        x,
                        y_min,
                        y_max,
                        alpha=0.2,
                    )
            else:
                if area:
                    plt.fill_between(
                        x,
                        np.array(y) - np.array(y_std),
                        np.array(y) + np.array(y_std),
                        alpha=0.2,
                    )

    # Labels & style
    plt.title(f"{METRICS[metric]} vs Difficulty", fontsize=14)
    plt.xlabel("Difficulty Level", fontsize=12)
    plt.ylabel(f"{METRICS[metric]} {UNITS[metric]}", fontsize=12)
    plt.xticks(range(min(diffs), max(diffs) + 1), rotation=45)
    plt.grid(True, linestyle="--", linewidth=0.5, alpha=0.7)
    plt.legend(title="Method", fontsize=10)
    plt.tight_layout()
    plt.show()


def plot_qubits(results: list[Result], ignore_diff=[]):
    """Plot per-iteration qubit count for one curve per difficulty level.

    The qubit count grows as the SCP master accumulates new cuts (rows)
    and possibly new predicates (columns), so the curve is monotone
    non-decreasing within a single Benders run.
    """
    diffs = []
    for r in results:
        d = DIFFICULTY[str(datetime.timedelta(seconds=r.earliest))]
        if d in diffs:
            continue
        else:
            diffs.append(d)
        label = f"Difficulty Level {d}"
        y = r.qubit_cnts
        x = range(1, len(y) + 1)
        plt.plot(x, y, marker="o", label=label)
    plt.title("Qubit Count Evolution through Iterations")
    plt.xlabel("Iteration")
    plt.ylabel("Qubit Count")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.show()


def get_constraints(times: list[str]):
    """Build the constraint tuple for each ``EARLY`` time and return them.

    Returns a dict ``earliest_seconds -> (fixed, selectable, deviations)``
    suitable as input to ``run_benders_experiment`` /
    ``run_centralized_exp``.
    """
    net = "data/network_OEOEB.txt"
    trains = "data/train_OEOEB.txt"
    ts = parse_train_file(trains)
    G = parse_network_file(net)
    constrs = {}
    for time in times:
        early = parse_time(time)
        c = build_constraints(G, ts, early=early)
        constrs.update({early: c})
    return constrs


def load_constrs(filename=CONSTRPKL):
    """Loads constraints from file."""
    try:
        with open(filename, "rb") as cfile:
            return pickle.load(cfile)
    except (EOFError, FileNotFoundError):
        return {}


def save_constrs(constrs: dict, filename=CONSTRPKL):
    """Saves constraints in file."""
    c = load_constrs(filename)
    c.update(constrs)
    with open(filename, "wb") as cfile:
        pickle.dump(c, cfile)


def run_benders_experiment(
    constrs: dict, strat: str, samples: int, filename: str, **kwargs
) -> list[Result]:
    """Run the Benders algorithm ``samples`` times per constraint instance.

    Each constraint set in ``constrs`` (keyed by earliest-time seconds) is
    solved ``samples`` times with SCP strategy ``strat`` (``greedy`` /
    ``gurobi`` / ``quantum``); ``**kwargs`` are passed through to
    ``benders_algorithm`` (``depth``, ``steps``, ``simulate``, ...).
    Each ``Result`` is appended to ``filename`` *as it completes* so
    long-running hardware sweeps do not lose data on crash.
    """
    rs = []
    for time, constr in constrs.items():
        print(f"Solving constraints for earliest time: {time}")
        for _ in range(samples):
            res: Result = benders_algorithm(
                constr, platforms=RISKS, scp_strat=strat, **kwargs
            )
            res.earliest = time
            res.method = strat
            save_results([res], filename=filename)
            rs.append(res)
    return rs


def run_centralized_exp(constrs: dict, samples: int, filename: str) -> list[Result]:
    """Run the centralised Gurobi MILP baseline ``samples`` times per instance.

    Counterpart to ``run_benders_experiment`` for the non-decomposed
    reference solver. Results are streamed to ``filename`` as they
    complete.
    """
    rs = []
    for time, constr in constrs.items():
        print(f"Solving constraints for earliest time: {time}")
        for _ in range(samples):
            res: Result = central_algorithm(constr, platforms=RISKS)
            res.earliest = time
            res.method = "centralized"
            save_results([res], filename=filename)
            rs.append(res)
    return rs
