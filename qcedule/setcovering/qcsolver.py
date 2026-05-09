"""
This module is deprecated.
Implement a SCP solver with Quantum Computing.
"""

# Note: We manually implement the cost and mixer layers instead of using `qml.evolve()`,
# since `qml.evolve()` caused execution errors in the current PennyLane setup. ¯\_(ツ)_/¯
import logging
import os
import pickle
import random
import warnings
from itertools import combinations
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd
import pennylane as qml
from dotenv import load_dotenv
from pennylane.devices import Device
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel
from qiskit_ibm_runtime import QiskitRuntimeService, exceptions
from qiskit_ibm_runtime.fake_provider import FakeBrisbane
from scipy.optimize import minimize

QUBITCOUNT = "qcount.pkl"
logging.getLogger("qiskit_ibm_runtime").setLevel(logging.INFO)
# load token from .env
load_dotenv()
token = os.getenv("QUANTUM_IBM_TOKEN")
QUANTUM_IBM_INSTANCE = os.getenv("QUANTUM_IBM_INSTANCE")
if not token or token.strip() == "":
    raise RuntimeError("Please create a .env with QUANTUM_IBM_TOKEN = your_token_here")

# TODO: after 1.07.25 use channel="ibm_quantum_platform"
try:
    QiskitRuntimeService.save_account(
        instance=QUANTUM_IBM_INSTANCE,
        token=token,
        overwrite=True,
        set_as_default=True,
    )
    service = QiskitRuntimeService()
except exceptions.IBMNotAuthorizedError as e:
    warnings.warn(
        "Something went wrong with autorization:\n"
        + e.message
        + "\nToken: "
        + token
        + "\nProceeding without RuntimeService."
    )
    service = None


# set parameters
FAKEBACKEND = FakeBrisbane()
SIMULATOR = AerSimulator()
LAYERS = 2
SHOTS = 10
STEPS = 10
NOISE = NoiseModel.from_backend(FAKEBACKEND)


# choose device: simulator or real hardware
def get_device(
    data: pd.DataFrame,
    backend_name: str | None = None,
    shots: int = SHOTS,
) -> Device:
    """
    Return a PennyLane device:

      * backend_name is None         → Aer simulator
      * backend_name == "least_busy" → query service.least_busy(...)
      * otherwise                    → use the specified IBM backend
    """

    wire_labels = WIRES.values()
    n_qubits = len(wire_labels)

    # Simulator
    if backend_name is None:
        # return qml.device(
        #     "qiskit.aer",
        #     wires=wire_labels,
        #     shots=shots,
        #     noise_model=NOISE,
        # )
        return qml.device("lightning.qubit", wires=wire_labels, shots=shots)

    # Least‐busy hardware
    if backend_name == "least_busy":
        lb_backend = service.least_busy(
            operational=True,
            simulator=False,
            min_num_qubits=n_qubits,
        )
        return qml.device(
            "qiskit.remote",
            service=service,
            backend=lb_backend,
            wires=wire_labels,
            shots=shots,
        )

    # Specific named hardware (e.g. "ibmq_brisbane")
    return qml.device(
        "qiskit.remote",
        service=service,
        backend=backend_name,
        wires=wire_labels,
        shots=shots,
    )


# -------------------------------------------------


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
    # qml.Barrier()


def mc_bitflip_mixerH(data: pd.DataFrame) -> qml.Hamiltonian:
    """Implements a multi-controlled Mixer Hamiltonian."""
    pass


def cost_layer(gamma, wires):
    """Applies the cost layer with RZ rotations."""
    for w in wires:
        qml.RZ(gamma, wires=w)


def circuit(data: pd.DataFrame, order, params, depth=LAYERS):
    """Defines the QAOA quantum circuit using global COST."""
    wires = [WIRES[c] for c in data.columns]
    gammas = params[0::2]
    betas = params[1::2]
    for w in wires:
        qml.X(w)
    for d in range(depth):
        cost_layer(gammas[d], wires=wires)
        mc_bitflip_mixer(data, betas[d], order)


def init_wire_map(data: pd.DataFrame):
    global WIRES
    WIRES = {label: data.columns.get_loc(label) for label in data.columns}
    WIRES.update({index: index + len(data.columns) for index in data.index})
    try:
        with open(QUBITCOUNT, "rb") as f:
            qcounts: list = pickle.load(f)
    except (EOFError, FileNotFoundError):
        qcounts = []
    with open(QUBITCOUNT, "wb") as f:
        qcounts.append(len(WIRES))
        pickle.dump(qcounts, f)


def get_order(data: pd.DataFrame, order):
    if order is None:
        return data.columns
    elif order:
        return data.sum().sort_values().index
    else:
        sorted = [c for c in data.columns]
        random.shuffle(sorted)
        return sorted


def qaoa(
    data: pd.DataFrame,
    *,
    order: Any = None,
    depth: int = LAYERS,
    backend_name: str | None = None,
    shots: int = SHOTS,
    steps: int = STEPS,
) -> tuple:
    """Runs the full QAOA workflow and returns optimized parameters and output distribution."""
    if data.empty or data.shape[1] == 0:
        raise ValueError("Input DataFrame is empty or has no columns.")
    init_wire_map(data)
    dev = get_device(data, backend_name=backend_name, shots=shots)
    params = optimize_parameters(data, dev, depth=depth, steps=steps, order=order)

    @qml.qnode(dev)
    @qml.compile
    def final_circuit():
        circuit(data, params=params, depth=depth, order=get_order(data, order))
        return qml.counts(wires=[WIRES[c] for c in data.columns])

    counts = final_circuit()
    # n_qubits = len(qubit_labels)
    # bitstrings = [format(i, f"0{n_qubits}b") for i in range(2**n_qubits)]

    # Visualization (can be commented out if needed)
    # plt.figure(figsize=(10, 4))
    # plt.bar(bitstrings, counts)
    # plt.xlabel("Bitstring (subset selection)")
    # plt.ylabel("Probability")
    # plt.title("QAOA Output Distribution")
    # plt.xticks(rotation=45)
    # plt.tight_layout()
    # plt.show()

    # fig, ax = qml.draw_mpl(final_circuit)()
    # fig.suptitle("QAOA Circuit", fontsize=14)
    # fig.tight_layout()
    # plt.show()

    return counts


def quantum_solve(data: pd.DataFrame, **qaoa_kwargs) -> set[Any]:
    """Solves SCP with QuantumComputing."""
    counts: dict = qaoa(data, **qaoa_kwargs)
    bitstring = max(counts, key=counts.get)
    selected_subsets = {
        label for label, bit in zip(data.columns, bitstring) if int(bit)
    }
    return selected_subsets


def count_cost(counts: dict):
    c = 0
    for string, count in counts.items():
        ones = string.count("1")
        c += ones * count
    return c


def optimize_parameters(
    data: pd.DataFrame,
    dev,
    depth: int = 1,
    initial_params: list = None,
    method: str = "COBYLA",
    steps: int = 10,
    order=None,
) -> tuple[list, float]:
    """
    Optimizes the parameters for the quantum circuit.

    Args:
        data (pd.DataFrame): Problem instance as DataFrame.
        dev: Device running the quantum circuit.
        depth (int, optional): Depth of the circuit. Defaults to 1.
        steps (int, optional): Number of optimization steps. Defaults to 100.
        learning_rate (float, optional): Learning rate for optimization. Defaults to 0.01.
        initial_params (list, optional): Initial parameters for the circuit. Defaults to None.
        optimizer_type (str, optional): Optimizer to use. Defaults to 'gradient_descent'.

    Returns:
        tuple[list, float]: Optimized parameters and the minimum cost.
    """
    sorted = get_order(data, order)
    if initial_params is None:
        initial_params = [random.uniform(0, np.pi) for _ in range(depth * 2)]

    # Cost function

    @qml.qnode(dev)
    @qml.compile
    def cost_function(params):
        circuit(data, params=params, depth=depth, order=sorted)
        return qml.counts(wires=[WIRES[c] for c in data.columns])

    def cost(params):
        return count_cost(cost_function(params))

    # optimization loop
    params = minimize(cost, initial_params, method=method, options={"maxiter": steps}).x

    return params


# === Testing part ====
if __name__ == "__main__":
    # Minimal example: 5 elements, 3 subsets
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

    p = quantum_solve(data)
    print(p)

################################
# example usage of quantum_solve
# quantum_solve(data)                                   # simulator
# quantum_solve(data, backend_name="least_busy")        # least‐busy hardware
# quantum_solve(data, backend_name="ibmq_brisbane")     # specific hardware
################################
