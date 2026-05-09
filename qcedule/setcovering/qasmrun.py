"""Runs a circuit on qiskit infrastructure based on its qasm representation."""

import os
import pickle
from collections import defaultdict
from datetime import datetime

from dotenv import load_dotenv
from qiskit import qasm2
from qiskit.transpiler import generate_preset_pass_manager
from qiskit_aer import AerSimulator, noise
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
from qiskit_ibm_runtime.exceptions import RuntimeJobFailureError
from qiskit_ibm_runtime.fake_provider import FakeBrisbane as Fake

TQUEUE = "tqueue.pkl"
NOISE = noise.NoiseModel.from_backend(Fake())
DEFAULTBACKEND = AerSimulator()
RETRIES = 5


def init_service():
    """Initializes Runtime Service."""
    load_dotenv()
    TOKEN = os.getenv("QUANTUM_IBM_TOKEN")
    QiskitRuntimeService.save_account(
        token=TOKEN,
        overwrite=True,
        set_as_default=True,
    )
    global SERVICE
    SERVICE = QiskitRuntimeService()


def store_queuetime(time: float) -> None:
    """Stores the time spent in queue."""
    try:
        with open(TQUEUE, "rb") as f:
            total_queue: float = pickle.load(f)
    except (EOFError, FileNotFoundError):
        total_queue = 0
    with open(TQUEUE, "wb") as f:
        total_queue += time
        pickle.dump(total_queue, f)


def run_circ(qasm: str, qcount: int, non_anc_bits: int, simulate=True) -> defaultdict:
    """Execute an OpenQASM 2 circuit and return non-ancilla measurement counts.

    Pipeline: ``qasm2.loads`` -> Qiskit preset transpiler (level 1) targeting
    the chosen backend -> ``SamplerV2`` job. Hardware path uses
    ``ibm_torino`` (Heron, 133 qubits). The returned counts are *grouped by
    the last ``non_anc_bits``* of each bitstring, i.e. the SCP solution
    bits without the element ancillas, since IBM exposes results MSB-first.

    Args:
        qasm: OpenQASM 2 source produced by PennyLane's tape exporter.
        qcount: Total number of wires (subsets + ancillas).
        non_anc_bits: Number of subset (non-ancilla) qubits to keep.
        simulate: If True use the local ``AerSimulator``; if False submit
            a real-hardware job via Qiskit Runtime. Hardware execution
            stores the queue time via ``store_queuetime``.
    """

    # Getting the backend
    if simulate:
        backend = DEFAULTBACKEND
    else:
        # print(SERVICE.backends())
        backend = SERVICE.backend("ibm_torino")

    # Preparing the circuit
    circuit = qasm2.loads(qasm)
    pm = generate_preset_pass_manager(optimization_level=1, backend=backend)
    isa_circuit = pm.run(circuit)

    # Running the circuit
    sampler = SamplerV2(mode=backend)
    print(f"Now starting job on {backend.name}...")
    for _ in range(RETRIES):
        try:
            job = sampler.run([(isa_circuit,)], shots=128)
            print(f"Job ID: {job.job_id()}")
            res = job.result()
            break
        except RuntimeJobFailureError as e:
            if "Temporary Internal Error" in str(e):
                print(
                    f"Encountered Temporary Internal Error for job {job.job_id()}. Running again..."
                )
            else:
                raise e
    # Retrieving queue time
    timestamps = job.metrics()["timestamps"]
    created = timestamps["created"]
    running = timestamps["running"]
    tc = created if isinstance(created, datetime) else datetime.fromisoformat(created)
    tr = running if isinstance(running, datetime) else datetime.fromisoformat(running)
    # queue_time = timestamps["running"] - timestamps["created"]
    tdelta = tr - tc
    store_queuetime(tdelta.total_seconds())

    counts = res[0].data.c.get_counts()

    # Grouping counts by non-ancilla qubits.
    non_anc_counts = defaultdict(int)
    for bits, val in counts.items():
        last_bits = bits[-non_anc_bits:]
        non_anc_counts[last_bits] += val

    return non_anc_counts
