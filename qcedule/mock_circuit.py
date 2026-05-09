import pennylane as qml
from pennylane import numpy as np
import matplotlib.pyplot as plt
from pennylane import draw_mpl

# Cicuit initialization
n_qubits = 7  # amount of selectables (i.e.)
dev = qml.device("default.qubit", wires=n_qubits)

# Circuit in details
@qml.qnode(dev)
def train_schedule_ansatz(params):
    # Initiliazing the superposition
    for i in range(n_qubits):
        qml.Hadamard(wires=i)

    # QAOA cost unitary (TO DO)
    qml.templates.StronglyEntanglingLayers(params, wires=range(n_qubits)) # imitation of QAOA from Pennylane library

    # Mixer unitary (just X-Gates for now; not full, only π/4)
    for i in range(n_qubits):
        qml.RX(np.pi / 4, wires=i)

    # Meausuring
    return qml.probs(wires=range(n_qubits))

# Testing the scheme
params = np.random.randn(1, n_qubits, 3)  # Placeholder parameters: shape (layers, qubits, parameters per qubit). Here we use one layer and three rotation parameters per qubit. These will be optimized later during QAOA training.
probs = train_schedule_ansatz(params)
print("Probabilities of the configuration:", probs)



# Getting probabilities
probs = train_schedule_ansatz(params)

# Binary marks of configurations
bitstrings = [format(i, f'0{n_qubits}b') for i in range(2 ** n_qubits)]

# Plotting
    # Diagramm
plt.figure(figsize=(10, 5))
plt.bar(bitstrings, probs)
plt.xticks(rotation=90)
plt.xlabel("Bitstring")
plt.ylabel("Probability")
plt.title("Configuration probability")
plt.tight_layout()
plt.show()

    # Circuit
fig, ax = draw_mpl(train_schedule_ansatz)(params)
fig.suptitle("Quantum Circuit for Train Scheduling (Mock Version)", fontsize=14)
fig.tight_layout()
plt.show()