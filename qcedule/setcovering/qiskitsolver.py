"""
This module is deprecated.
Implement a SCP solver with Quantum Computing.
"""

# Note: We manually implement the cost and mixer layers instead of using `qml.evolve()`,
# since `qml.evolve()` caused execution errors in the current PennyLane setup. ¯\_(ツ)_/¯

import os
import random
from itertools import combinations
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from qiskit import (
    AncillaRegister,
    QuantumCircuit,
    QuantumRegister,
)
from qiskit.result import QuasiDistribution
from qiskit.transpiler import generate_preset_pass_manager
from qiskit.transpiler.passes import HLSConfig
from qiskit.visualization import circuit_drawer
from qiskit_aer import AerSimulator
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
from scipy.optimize import minimize

HLS = HLSConfig(synthesis_methods={"mcx": "noancilla"})
load_dotenv()
token = os.getenv("QUANTUM_IBM_TOKEN")
if not token or token.strip() == "":
    raise RuntimeError("Please create a .env with QUANTUM_IBM_TOKEN = your_token_here")
LAYERS = 2
SHOTS = 10
DEFAULTBACKEND = AerSimulator()
QiskitRuntimeService.save_account(
    token=token,
    overwrite=True,
    set_as_default=True,
)
SERVICE = QiskitRuntimeService()
for backend in SERVICE.backends():
    print(backend)


def get_backend(simulator=True):
    if simulator:
        return DEFAULTBACKEND
    else:
        # backend = SERVICE.least_busy(
        #     operational=True,
        #     simulator=False,
        #     min_num_qubits=QCOUNT,
        # )
        # print(f"Using: {backend} of class {type(backend)}")
        return SERVICE.backend("ibm_brisbane")


# === Temporary helper functions ===


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


def qaoa_circ(data: pd.DataFrame, params, depth=LAYERS):
    G = constraint_graph(data)
    q = QuantumRegister(size=len(data.columns))
    a = AncillaRegister(size=len(data.index) + 1)
    qc = QuantumCircuit(q, a)
    sets = [WIRES[c] for c in data.columns]
    gammas = params[0::2]
    betas = params[1::2]
    for s in sets:
        qc.x(s)
    for d in range(depth):
        for s in sets:
            qc.rz(gammas[d], s)
        qc.x(q)
        qc.x(a)
        for c, contents in data.items():
            # Get all neighbouring nodes and inhabitants of subset c
            nb = [n for n in G.neighbors(c)]
            inhabitants = [elem for elem, b in contents.items() if b]
            # For each inhabitant, use an ancilla qubit to encode
            # if any neighbour containing that inhab is selected
            for elem in inhabitants:
                cond = [WIRES[n] for n in nb if data.at[elem, n]]
                qc.mcx([q[c] for c in cond], a[elem])
            qc.x(WIRES[c])
            controls = [a[i] for i in inhabitants]
            qc.mcx(controls, a[-1])
            qc.crx(theta=betas[d], control_qubit=a[-1], target_qubit=q[WIRES[c]])
            qc.mcx(controls, a[-1])

            qc.x(WIRES[c])
            # Clean up
            for elem in inhabitants:
                cond = [WIRES[n] for n in nb if data.at[elem, n]]
                qc.mcx([q[c] for c in cond], a[elem])
        qc.x(q)
        qc.x(a)
    qc.measure_all()
    return qc


def init_wire_map(data: pd.DataFrame):
    global WIRES
    WIRES = {label: data.columns.get_loc(label) for label in data.columns}
    global QCOUNT
    QCOUNT = len(data.columns) + len(data.index)


def qaoa(data: pd.DataFrame, depth=LAYERS, shots=SHOTS, simulator=True) -> tuple:
    """Runs the full QAOA workflow and returns optimized parameters and output distribution."""
    if data.empty or data.shape[1] == 0:
        raise ValueError("Input DataFrame is empty or has no columns.")
    init_wire_map(data)
    backend = get_backend(simulator=simulator)
    sampler = SamplerV2(mode=backend, options={"default_shots": shots})
    sampler.options
    params = optimize_parameters(data, depth=depth, shots=shots, backend=backend)

    qc = qaoa_circ(data, params)
    pm = generate_preset_pass_manager(
        optimization_level=1, backend=backend, hls_config=HLS
    )
    circ = pm.run(qc)
    job = sampler.run([circ])
    print(job.job_id())
    counts = job.result()[0].data.meas.get_counts()
    return counts


def qiskit_solve(data: pd.DataFrame, **kwargs) -> set[Any]:
    """Solves SCP with QuantumComputing."""
    counts: dict = qaoa(data, **kwargs)
    bitstring = reversed(max(counts, key=counts.get))
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
    depth: int = 1,
    initial_params: list = None,
    method: str = "COBYLA",
    steps: int = 10,
    shots: int = SHOTS,
    backend=DEFAULTBACKEND,
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

    if initial_params is None:
        initial_params = [random.uniform(0, np.pi) for _ in range(depth * 2)]

    # Cost function
    sampler = SamplerV2(mode=backend, options={"default_shots": shots})
    print(type(sampler))
    pm = generate_preset_pass_manager(
        optimization_level=1, backend=backend, hls_config=HLS
    )

    def cost(params):
        qc = qaoa_circ(data, params)
        circ = pm.run(qc)
        print(circ.count_ops())
        circuit_drawer(circ, filename="circ", output="mpl")
        try:
            job = sampler.run([circ])
            print(job.job_id())
            print(job.status())
        except KeyboardInterrupt:
            print(job.errored())
            print(job.status())
            job.cancel()
            raise RuntimeError()

        try:
            counts = job.result()
        except Exception as e:
            print(f"    ❌ Job execution failed: {e}")
            print(f"    📊 Job ID: {job.job_id()}")
            print(f"    📊 Job status: {job.status()}")
            raise
        quasi_dists = []
        metadata = []
        for i, pub_result in enumerate(counts):
            try:
                # --- THIS IS THE FIX ---
                # At optimization_level=1, the classical register data may be unnamed.
                # We need a more robust way to access it.
                if hasattr(pub_result.data, "c"):
                    counts = pub_result.data.c.get_counts()
                elif hasattr(pub_result.data, "meas"):
                    counts = pub_result.data.meas.get_counts()
                else:
                    # If no named register is found, access the data directly.
                    # The DataBin object can be iterated over to get its values.
                    print(
                        f"    ⚠️ Circuit {i}: No 'c' or 'meas' register found, accessing data directly..."
                    )
                    data_fields = list(vars(pub_result.data).values())
                    if not data_fields:
                        raise ValueError(f"No measurement data found in result {i}")
                    counts = data_fields[0].get_counts()
                # --- END FIX ---

                total_shots = sum(counts.values()) if counts else 1
                quasi_dist_dict = {
                    int(bitstring, 2)
                    if isinstance(bitstring, str)
                    else bitstring: count / total_shots
                    for bitstring, count in counts.items()
                }

                quasi_dists.append(QuasiDistribution(quasi_dist_dict))

                pub_metadata = (
                    pub_result.metadata.copy()
                    if hasattr(pub_result, "metadata")
                    else {}
                )
                pub_metadata["shots"] = total_shots
                metadata.append(pub_metadata)

            except Exception as e:
                print(f"    ❌ Error processing result {i}: {e}")
                raise
        return count_cost(counts)

    # optimization loop
    params = minimize(cost, initial_params, method=method, options={"maxiter": steps}).x

    return params


# === Testing part ====
if __name__ == "__main__":
    # Minimal example: 5 elements, 3 subsets
    superset = {0, 1}
    a = {0, 1}
    b = {0}
    c = {1}
    a_, b_, c_ = "a", "b", "c"
    subsetlabels = [b_, a_, c_]
    subsets = [b, a, c]
    matrix = np.matrix([[i in j for j in subsets] for i in superset])
    data = pd.DataFrame(matrix, columns=subsetlabels)

    p = qiskit_solve(data, simulator=False)
    print(p)
