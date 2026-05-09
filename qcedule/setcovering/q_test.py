from qiskit import QuantumCircuit
from qiskit_ibm_runtime import QiskitRuntimeService, Sampler
from dotenv import load_dotenv
import os

load_dotenv()
token = os.getenv("QUANTUM_IBM_TOKEN")
if not token:
    raise RuntimeError("QUANTUM_IBM_TOKEN not found in environment")

service = QiskitRuntimeService(channel="ibm_cloud", token=token)

backend = service.backend("ibm_brisbane")
print(f"Using backend: {backend.name}")

# Just X-Gate + Measuring
qc = QuantumCircuit(1)
qc.x(0)
qc.measure_all()

print("Circuit:")
print(qc)


sampler = Sampler(mode=backend)

job = sampler.run([qc])
result = job.result()


dist = result.quasi_distr[0]
print(dist)


job = sampler.run(circuits=[qc], backend=backend_name)
result = job.result()


print(f"\n Result: {result.quasi_dists[0]}")