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
    """Return a PennyLane device"""
    wire_labels = WIRES.values()
    return qml.device("lightning.qubit", wires=wire_labels, shots=shots)


# === Temporary (?) helper functions ===


def qOr(qubits: list, target):
    """Implements logical Or with quantum gates.
    Optimized version expects X gates before and after are already applied."""
    if not qubits:
        qml.X(target)
    else:
        qml.MultiControlledX(wires=qubits + [target])


def constraint_graph(data: pd.DataFrame):
    """Builds constraint graph:
    - subsets are the nodes
    - edge if two nodes intersect"""
    C = nx.Graph()
    C.add_nodes_from(data.columns)
    for (s1, c1), (s2, c2) in combinations(data.items(), 2):
        if c1.dot(c2):
            C.add_edge(s1, s2)
    return C


def mc_bitflip_mixer(data: pd.DataFrame, beta: float, order):
    """Implements full Mixer."""
    N = constraint_graph(data)
    # For each subset we add RX controlled by an Or-expression:
    # Preparing states for all upcoming Ors:
    for c in data.columns:
        qml.X(WIRES[c])
    for i in data.index:
        qml.X(WIRES[i])
    for c in order:
        contents = data[c]
        # Get all neighbouring nodes and inhabitants of subset c
        nb = [n for n in N.neighbors(c)]
        inhabitants = [elem for elem, b in contents.items() if b]
        # For each inhabitant, use an ancilla qubit to encode
        # if any neighbour containing that inhab is selected
        for elem in inhabitants:
            cond = [WIRES[n] for n in nb if data.at[elem, n]]
            qOr(cond, WIRES[elem])
        # Wrap RX in X gates to not let them infer with the or logic.
        qml.X(WIRES[c])
        # Use ancillas to control the bitflip
        qml.ctrl(qml.RX(phi=beta, wires=WIRES[c]), [WIRES[i] for i in inhabitants])
        qml.X(WIRES[c])
        # Clean up ancillas
        for elem in inhabitants:
            cond = [WIRES[n] for n in nb if data.at[elem, n]]
            qOr(cond, WIRES[elem])
    # Cleaning up/Reverting initial X gates
    for c in data.columns:
        qml.X(WIRES[c])
    for i in data.index:
        qml.X(WIRES[i])


def cost_layer(gamma, wires):
    """Applies the cost layer with RZ rotations."""
    for w in wires:
        qml.RZ(gamma, wires=w)


@partial(
    decompose, gate_set={qml.RX, qml.RZ, qml.RY, qml.CNOT, qml.Toffoli, qml.PauliX}
)
def circuit(data: pd.DataFrame, order, params, depth=LAYERS):
    """Defines the QAOA quantum circuit."""
    wires = [WIRES[c] for c in data.columns]
    gammas = params[0::2]
    betas = params[1::2]
    for w in wires:
        qml.X(w)
    for d in range(depth):
        cost_layer(gammas[d], wires=wires)
        mc_bitflip_mixer(data, betas[d], order)


def init_wire_map(data: pd.DataFrame):
    """Initializes a mapping from data column and index to circuit wires."""
    global WIRES
    WIRES = {label: data.columns.get_loc(label) for label in data.columns}
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
    """Chooses an order of the data columns."""
    if order is None:
        return data.columns
    elif order:
        return data.sum().sort_values().index
    else:
        sorted = [c for c in data.columns]
        random.shuffle(sorted)
        return sorted


def count_cost(counts: dict):
    """Computes the cost of a counts dictionary."""
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
    """Runs the full QAOA workflow and returns optimized parameters and output distribution."""

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
    """Solves SCP with QuantumComputing."""
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
