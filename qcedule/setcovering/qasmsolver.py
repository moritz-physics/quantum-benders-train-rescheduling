"""Implement a SCP solver with Quantum Computing."""

# Note: We manually implement the cost and mixer layers instead of using `qml.evolve()`,
# since `qml.evolve()` caused execution errors in the current PennyLane setup. ¯\_(ツ)_/¯
import os
import pickle
import random
from functools import partial
from itertools import combinations
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd
import pennylane as qml
from pennylane.devices import Device
from pennylane.tape import QuantumTape
from pennylane.transforms import decompose
from scipy.optimize import minimize

from .qasmrun import TQUEUE, run_circ

QUBITCOUNT = "qcount.pkl"
LAYERS = 2
SHOTS = 10
STEPS = 10


# choose device: simulator or real hardware
def get_device(shots: int = SHOTS) -> Device:
    """Return a PennyLane ``lightning.qubit`` device sized to the wire map.

    PennyLane is only used to *construct* the circuit; execution always
    happens through the OpenQASM round-trip in ``qasmrun.run_circ``, so we
    pick the cheapest local device that supports finite-shot sampling.
    """
    wire_labels = WIRES.values()
    return qml.device("lightning.qubit", wires=wire_labels, shots=shots)


# === Temporary (?) helper functions ===


def qOr(qubits: list, target):
    """Implement a logical OR of ``qubits`` into ``target`` with quantum gates.

    Caller convention: ``X`` gates are applied before and after the call to
    flip the basis so that an MCX on the (post-X) ``qubits`` realises an OR
    rather than an AND on the original qubits (De Morgan). The empty-OR
    case degenerates to a single X (OR over no inputs is identically False
    in the original basis, hence True after the surrounding X-flip).
    """
    if not qubits:
        # OR over no inputs -> constant False; in the X-flipped basis that
        # means the target should always be flipped.
        qml.X(target)
    else:
        # In the X-flipped basis an MCX realises a logical OR.
        qml.MultiControlledX(wires=qubits + [target])


def constraint_graph(data: pd.DataFrame):
    """Build the SCP constraint graph (nodes = subsets, edges = intersections).

    Two subsets are connected iff their Boolean column vectors share at
    least one element (i.e. their dot product is non-zero). This graph
    drives the intersection-aware mixer in ``mc_bitflip_mixer``.
    """
    C = nx.Graph()
    C.add_nodes_from(data.columns)
    for (s1, c1), (s2, c2) in combinations(data.items(), 2):
        if c1.dot(c2):
            C.add_edge(s1, s2)
    return C


def mc_bitflip_mixer(data: pd.DataFrame, beta: float, order):
    """Apply the intersection-aware multi-controlled bit-flip mixer.

    Constraint-preserving Hadfield-style mixer specialised to set cover:
    for every subset ``c`` we apply ``RX(beta)`` on the qubit of ``c``,
    multi-controlled by per-element ancillas that hold the predicate
    *"some neighbour of c containing this element is currently selected"*.
    Flipping ``c`` therefore only fires when removing ``c`` would still
    leave every element it contains covered by some neighbour, so amplitude
    can never leak into infeasible (uncovered) states.

    Args:
        data: SCP DataFrame (rows = elements, columns = subsets).
        beta: Mixer angle of the current QAOA layer.
        order: Iteration order over subset columns -- see ``get_order``.
    """
    # Constraint graph: nodes = subsets, edges = "share at least one element".
    N = constraint_graph(data)
    # Wrap every Or-computation in surrounding X gates so the MCX-based
    # `qOr` realises a logical OR (De Morgan). These outer X-flips put
    # everything in the basis the qOr helpers expect.
    for c in data.columns:
        qml.X(WIRES[c])
    for i in data.index:
        qml.X(WIRES[i])
    for c in order:
        contents = data[c]
        # Neighbours of c in the constraint graph and the elements that c covers.
        nb = [n for n in N.neighbors(c)]
        inhabitants = [elem for elem, b in contents.items() if b]
        # For each element e in c, compute on its ancilla the disjunction
        # "some neighbour of c that contains e is currently selected".
        for elem in inhabitants:
            cond = [WIRES[n] for n in nb if data.at[elem, n]]
            qOr(cond, WIRES[elem])
        # Locally invert c so the controlled RX flips amplitude *into*
        # "drop c" only if every inhabitant ancilla evaluates true.
        qml.X(WIRES[c])
        # Multi-controlled RX(beta): the feasibility-preserving mixer step.
        qml.ctrl(qml.RX(phi=beta, wires=WIRES[c]), [WIRES[i] for i in inhabitants])
        qml.X(WIRES[c])
        # Uncompute the inhabitant ancillas with the mirrored chain so
        # they are returned to |0> (in the X-flipped basis) before the
        # next subset is processed.
        for elem in inhabitants:
            cond = [WIRES[n] for n in nb if data.at[elem, n]]
            qOr(cond, WIRES[elem])
    # Revert the surrounding X-flip basis.
    for c in data.columns:
        qml.X(WIRES[c])
    for i in data.index:
        qml.X(WIRES[i])


def cost_layer(gamma, wires):
    """Apply the QAOA cost unitary ``exp(-i gamma sum_w Z_w / 2)``.

    The diagonal cost Hamiltonian is the sum of ``Z`` on every subset
    qubit, equivalent (up to constants) to the Hamming weight, i.e. the
    number of selected subsets. Implementing it as one ``RZ`` per wire is
    exact since the Pauli-Zs commute.
    """
    for w in wires:
        qml.RZ(gamma, wires=w)


@partial(
    decompose, gate_set={qml.RX, qml.RZ, qml.RY, qml.CNOT, qml.Toffoli, qml.PauliX}
)
def circuit(data: pd.DataFrame, order, params, depth=LAYERS):
    """The QAOA-variant ansatz used as SCP master.

    Layer structure (Hadfield-style alternating operator ansatz):
      1. ``X`` on every subset qubit -> the all-1 / "everything selected"
         state, which is trivially a cover and a natural seed for the
         constraint-preserving mixer.
      2. For each of ``depth`` layers, alternate the diagonal cost
         (``RZ(gamma)`` per subset qubit) and the intersection-aware mixer.

    The ``@decompose`` wrapper restricts the gate set so that the OpenQASM
    export to Qiskit transpiles cleanly onto IBM hardware native gates.
    """
    wires = [WIRES[c] for c in data.columns]
    # Even-indexed params are cost angles, odd-indexed are mixer angles.
    gammas = params[0::2]
    betas = params[1::2]
    # Initial state |1...1>: all predicates "disabled" -> trivial cover.
    for w in wires:
        qml.X(w)
    for d in range(depth):
        cost_layer(gammas[d], wires=wires)
        mc_bitflip_mixer(data, betas[d], order)


def init_wire_map(data: pd.DataFrame):
    """Allocate qubit wires for one SCP instance and log the qubit count.

    Layout: subset qubits first (one per column of ``data``), element
    ancillas after (one per row). The element ancillas are used by the
    intersection-aware mixer to compute, on the fly, whether dropping a
    subset would still leave each element covered by some neighbour.
    """
    global WIRES
    WIRES = {label: data.columns.get_loc(label) for label in data.columns}
    # Element ancillas are appended *after* all subset qubits so we can
    # cleanly slice off the SCP solution by looking only at the first
    # `len(data.columns)` measurement bits.
    WIRES.update({index: index + len(data.columns) for index in data.index})

    # Keeping track of qubit count
    try:
        with open(QUBITCOUNT, "rb") as f:
            qcounts: list = pickle.load(f)
    except (EOFError, FileNotFoundError):
        qcounts = []
    with open(QUBITCOUNT, "wb") as f:
        qcounts.append(len(WIRES))
        pickle.dump(qcounts, f)


def get_order(data: pd.DataFrame, order):
    """Choose the order in which subset qubits are visited by the mixer.

    The ordering matters because the mixer applies a sequence of
    multi-controlled flips, and earlier flips change the state observed by
    later ones.

    Args:
        data: SCP DataFrame.
        order: ``None`` -> default column order; truthy -> ascending by
            subset cardinality (smallest covers first); falsy non-None ->
            random shuffle.
    """
    if order is None:
        return data.columns
    elif order:
        return data.sum().sort_values().index
    else:
        sorted = [c for c in data.columns]
        random.shuffle(sorted)
        return sorted


def count_cost(counts: dict):
    """SCP-cost estimator from a measurement counts dict.

    The classical cost we minimise is the number of selected subsets, i.e.
    the Hamming weight of the bitstring. For a counts dict we sum
    ``hamming_weight(bitstring) * count`` -- a Monte-Carlo estimator (up to
    a shot-count scale) of the QAOA cost expectation.
    """
    c = 0
    for string, count in counts.items():
        ones = string.count("1")
        c += ones * count
    return c


def optimize_parameters(
    data: pd.DataFrame,
    dev: Device,
    depth: int = 1,
    initial_params: list = None,
    method: str = "COBYLA",
    steps: int = 10,
    order=None,
    simulate=True,
) -> list[float]:
    """
    Optimizes the parameters for the quantum circuit.

    Args:
        data (pd.DataFrame): Problem instance as DataFrame.
        dev: Device running the quantum circuit.
        depth (int, optional): Depth of the circuit. Defaults to 1.
        steps (int, optional): Number of optimization steps. Defaults to 100.
        method (str, optional): Optimization method. Defaults to COBYLA.
        initial_params (list, optional): Initial parameters for the circuit. Defaults to None.
        order : The order of the data columns.

    Returns:
        tuple[list, float]: Optimized parameters and the minimum cost.
    """
    sorted = get_order(data, order)
    if initial_params is None:
        initial_params = [random.uniform(0, np.pi) for _ in range(depth * 2)]

    # Cost function
    def cost(params):
        with QuantumTape() as tape:
            circuit(data, params=params, depth=depth, order=sorted)
        qasm = tape.to_openqasm(dev.wires)
        counts = run_circ(
            qasm=qasm,
            qcount=len(WIRES),
            non_anc_bits=len(data.columns),
            simulate=simulate,
        )
        return count_cost(counts)

    # optimization loop
    params = minimize(cost, initial_params, method=method, options={"maxiter": steps}).x

    return params


def qaoa(
    data: pd.DataFrame,
    *,
    order: Any = None,
    depth: int = LAYERS,
    simulate: bool = True,
    shots: int = SHOTS,
    steps: int = STEPS,
) -> tuple:
    """Drive one full QAOA iteration: parameter optimisation + final sample.

    Allocates wires for the SCP DataFrame, optimises ``(gamma, beta)``
    angles via COBYLA on the Hamming-weight cost, and re-runs the optimal
    circuit once to produce the final measurement counts that
    ``quantum_solve`` post-processes into a subset selection.
    """

    if data.empty or data.shape[1] == 0:
        raise ValueError("Input DataFrame is empty or has no columns.")
    # Initialize core variables
    init_wire_map(data)
    dev = get_device(shots=shots)
    # Optimize parameters
    params = optimize_parameters(
        data, dev, depth=depth, steps=steps, order=order, simulate=simulate
    )
    # Run with optimized paramters
    with QuantumTape() as tape:
        circuit(data, params=params, depth=depth, order=get_order(data, order))
    qasm = tape.to_openqasm(dev.wires)
    counts = run_circ(
        qasm=qasm, qcount=len(WIRES), non_anc_bits=len(data.columns), simulate=simulate
    )

    return counts


def quantum_solve(data: pd.DataFrame, **qaoa_kwargs) -> set[Any]:
    """Solve the SCP via the QAOA-variant ansatz and return selected subset labels.

    Drop-in replacement for the classical ``greedy_solve`` / ``gurobi_solve``
    used by the Benders master. Picks the most frequent measured bitstring
    as the SCP solution. ``data`` columns are read in left-to-right order;
    Qiskit / OpenQASM bit strings are right-to-left, so we ``reverse``.
    ``**qaoa_kwargs`` are forwarded to ``qaoa`` (depth, shots, steps, ...).
    """
    print("Starting solving with quantum...")
    # init_service()
    counts: dict = qaoa(data, **qaoa_kwargs)
    bitstring = reversed(max(counts, key=counts.get))
    selected_subsets = {
        label for label, bit in zip(data.columns, bitstring) if int(bit)
    }
    return selected_subsets


# === Testing part ====
if __name__ == "__main__":
    ################################
    # example usage of quantum_solve
    # quantum_solve(data)                                   # simulator
    # quantum_solve(data, backend_name="least_busy")        # least‐busy hardware
    # quantum_solve(data, backend_name="ibmq_brisbane")     # specific hardware
    ################################

    superset = set(range(14))
    a = {i for i in superset if i % 2}
    b = {i for i in superset if not i % 2}
    c = {0, 7}
    d = {1, 2, 8, 9}
    e = {3, 4, 5, 6, 10, 11, 12, 13}
    a_, b_, c_, d_, e_ = "a", "b", "c", "d", "e"
    subsetlabels = [d_, b_, e_, a_, c_]
    subsets = [d, b, e, a, c]
    matrix = np.matrix([[i in j for j in subsets] for i in superset])
    data = pd.DataFrame(matrix, columns=subsetlabels)
    # superset = {0, 1}
    # a = {0, 1}
    # b = {0}
    # c = {1}
    # a_, b_, c_ = "a", "b", "c"
    # subsetlabels = [b_, a_, c_]
    # subsets = [b, a, c]
    # matrix = np.matrix([[i in j for j in subsets] for i in superset])
    # data = pd.DataFrame(matrix, columns=subsetlabels)

    res = quantum_solve(data, simulate=True)
    print(res)

    with open(TQUEUE, "rb") as f:
        t = pickle.load(f)
        print(f"Total queuetime: {t}s")
    os.remove(TQUEUE)
    with open(QUBITCOUNT, "rb") as f:
        c = pickle.load(f)
        print(f"QubitCount: {c}")
    os.remove(QUBITCOUNT)
