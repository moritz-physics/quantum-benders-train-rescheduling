from qiskit_ibm_runtime import QiskitRuntimeService
from dotenv import load_dotenv
import os
import matplotlib.pyplot as plt
from collections import Counter

# === Load IBM Quantum token from .env file ===
load_dotenv()
token = os.getenv("QUANTUM_IBM_TOKEN")  #  Token loaded securely from .env

# === Connect to IBM Quantum service ===
service = QiskitRuntimeService(
    channel='ibm_quantum',
    instance='ibm-q/open/main',
    token=token
)

# === Fetch job and result ===
job_id = 'd1hpddxn2txg008eya60'   # <---- change ID to desired one 
job = service.job(job_id)
job_result = job.result()

# === Identify classical register used ===
pub_result = job_result[0]
classical_register = list(pub_result.data.keys())[0]
print(f"ℹ Classical register used: {classical_register}")

# === Get bitstring counts from job result ===
counts = pub_result.data[classical_register].get_counts()

# === Trim bitstrings to last N bits to match problem variables ===
N = 5  #  Keep only the last N bits (problem-specific)
trimmed_counts = Counter()
for bitstring, count in counts.items():
    trimmed = bitstring[-N:]  #  Keep last N bits
    trimmed_counts[trimmed] += count

# === Print top 10 trimmed bitstrings ===
print("\n🔍 Top 10 bitstrings (trimmed):")
for bitstring, count in trimmed_counts.most_common(10):
    print(f"{bitstring}: {count}")

# === Plot histogram of trimmed results ===
bitstrings = list(trimmed_counts.keys())
frequencies = list(trimmed_counts.values())

plt.figure(figsize=(10, 4))
plt.bar(bitstrings, frequencies)
plt.xlabel("Bitstring (subset selection)")
plt.ylabel("Counts")
plt.title(f"QAOA Output Distribution (job_id: {job_id})")
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
