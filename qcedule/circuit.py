import pennylane as qml
from pennylane import numpy as np
import matplotlib.pyplot as plt
from pennylane import qaoa, draw_mpl

# This function loads selectables from real data using paths.py
def load_selectables(train_file, network_file):
    from qcedule.io_utils.file_parser import parse_train_file, parse_network_file
    from qcedule.io_utils.paths import get_area_paths

    # Load train and network data
    trains = parse_train_file(train_file)
    network = parse_network_file(network_file)

    # Collect all selectables from all trains
    all_selectables = {}
    for train in trains:
        area_paths = get_area_paths(train, network)
        for key, path_list in area_paths.items():
            # Convert to consistent format: edge tuples only
            paths = [[(x, y, k) for x, y, k in p] for p in path_list]
            if key in all_selectables:
                all_selectables[key].extend(paths)
            else:
                all_selectables[key] = paths

    return all_selectables

# === Getting the output from paths.py ===
selectables = load_selectables("data/train_easy.txt", "data/network_easy.txt")
n_qubits = len(selectables)


# Number of binary decisions (1 per routing area)
n_qubits = len(selectables)
wires = list(range(n_qubits))

# QAOA depth
depth = 2

# Create device
dev = qml.device("default.qubit", wires=n_qubits)

# === Cost Hamiltonian ===
# For now, we assign dummy weights (e.g., penalty = 1 per selected option)
# Later, you can compute real penalties (e.g., delay times, conflicts)
cost_coeffs = [1.0 for _ in range(n_qubits)]
cost_ops = [qml.PauliZ(i) for i in range(n_qubits)]
cost_h = qml.Hamiltonian(cost_coeffs, cost_ops)

# === Mixer Hamiltonian ===
# Standard X mixer, applies to all qubits
mixer_h = qml.Hamiltonian([1.0] * n_qubits, [qml.PauliX(i) for i in range(n_qubits)])

# === Define QAOA Layer ===
def qaoa_layer(gamma, alpha):
    qaoa.cost_layer(gamma, cost_h)
    qaoa.mixer_layer(alpha, mixer_h)

# === Circuit: Hadfield-style, no Hadamards ===
def circuit(params, **kwargs):
    # Optionally: prepare an initial feasible state here
    # For example, qml.BasisState(np.array([0, 1]), wires=wires)
    qml.layer(qaoa_layer, depth, params[0], params[1])

# === QNode ===
@qml.qnode(dev)
def qaoa_circuit(params):
    circuit(params)
    return qml.probs(wires=wires)

# === Parameters (preliminary) ===
params = np.array([
    [0.5] * depth,  # gamma
    [0.5] * depth   # alpha
], requires_grad=True)

# === Run circuit ===
probs = qaoa_circuit(params)
bitstrings = [format(i, f"0{n_qubits}b") for i in range(2 ** n_qubits)]

# === Plotting ===
plt.figure(figsize=(10, 4))
plt.bar(bitstrings, probs)
plt.xlabel("Bitstring (selectable decisions)")
plt.ylabel("Probability")
plt.title("QAOA Output Distribution")
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

# === Optional: Show circuit ===
fig, ax = draw_mpl(qaoa_circuit)(params)
fig.suptitle("QAOA Circuit for Train Routing", fontsize=14)
fig.tight_layout()
plt.show()
