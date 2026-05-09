import json
import pickle
from dataclasses import asdict, dataclass, field

PICKLEFILE = "results.pkl"


@dataclass
class Result:
    """Self-contained record of one solver run.

    Holds the timetable solution, wall-clock time (queue-time subtracted
    on the quantum path), Benders iteration count, total + relative
    deviation, per-iteration and peak qubit counts, and metadata
    identifying the run (``method``, ``solver``, ``earliest``) so a list
    of these can be plotted directly by ``exp_framework``.
    """
    model: dict = field(default_factory=dict)
    time: float = 0.0
    iter_num: int = 0
    total_dev: float = 0.0
    rel_dev: float = 1.0
    qubit_cnts: list = field(default_factory=list)
    max_qubits: int = 0
    method: str = ""
    solver: str = ""
    earliest: int = 0

    def save(self, path: str):
        """Dump this result as a JSON file."""
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @staticmethod
    def from_json(path: str) -> "Result":
        """Load a previously-saved JSON result file."""
        with open(path, "r") as f:
            data = json.load(f)
        return Result(**data)


# === manage results file ===


def load_results(filename=PICKLEFILE) -> list[Result]:
    """Loads list of results from a pickle file."""
    try:
        with open(filename, "rb") as pfile:
            return pickle.load(pfile)
    except (EOFError, FileNotFoundError):
        return []


def save_results(results: list[Result], filename=PICKLEFILE) -> None:
    """Saves results into list in a pickle file"""
    reslist = load_results(filename)
    reslist += results
    with open(filename, "wb") as pfile:
        pickle.dump(reslist, pfile)


def clean_results(filename=PICKLEFILE):
    """Truncate a results pickle to an empty list (for re-running a sweep)."""
    with open(filename, "wb") as pfile:
        pickle.dump([], pfile)


# === Relative Delay Calculation ===


def add_relative_delay(results: list[Result]):
    """Adds a new field 'reldelay' to each result: delay / centralized delay."""
    # Find best (lowest) delay for each 'earliest'
    base = {}
    for r in results:
        if r.method == "centralized":
            base[r.earliest] = r.total_dev
    # Add reldelay = this delay / centralized delay
    for r in results:
        base_delay = base.get(r.earliest, 1)
        r.rel_dev = ((r.total_dev) / base_delay - 1) * 100 if base_delay else 0
