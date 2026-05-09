# Quantum-Hybrid Benders Decomposition for Railway Timetable Rescheduling

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Qiskit](https://img.shields.io/badge/Qiskit-IBM%20Runtime-6929C4?logo=ibm&logoColor=white)](https://www.ibm.com/quantum/qiskit)
[![IBM Quantum](https://img.shields.io/badge/IBM%20Quantum-Heron%20%2F%20Eagle-052FAD?logo=ibm&logoColor=white)](https://quantum.ibm.com/)
[![Z3](https://img.shields.io/badge/Z3-SMT%20solver-2A579A)](https://github.com/Z3Prover/z3)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#license)

> Industry–academic collaboration: **LMU Munich × Siemens AG × QAR Lab**

## 👥 Team — group project at LMU Munich

> **This was a five-person team project.** All five team members contributed to the design, implementation, experiments, and analysis described below. This repository is mirrored from our group's LMU LRZ GitLab to my personal GitHub for portfolio purposes; the work itself is collective.

| Team member | Affiliation |
| --- | --- |
| **Moritz Heidtmann** | LMU Munich |
| **Andrei Zubarev** | LMU Munich |
| **Daniel Kratzer** | LMU Munich |
| **Kilian Krüger** | LMU Munich |
| **Emanuele Poggi** | LMU Munich |

Per-person contributions are listed in the [Collaboration](#collaboration) section at the bottom of this README.

## Abstract

> Railway operators must restore safe, minimally delayed timetables within
> minutes after disruptions, yet traditional monolithic mixed-integer
> models scale poorly as hundreds of trains interact on dense networks. We
> address this by proposing a **quantum-hybrid Benders decomposition** that
> decouples continuous timing from combinatorial precedence decisions. Our
> framework translates industrial track and schedule data into fixed and
> selectable lower-bound constraints, then uses a Z3-based satisfiability
> sub-problem with "bucketed" deviation predicates as assumptions. Minimal
> unsatisfiable cores serve as Benders cuts in a set-cover master problem,
> which we solve via a **Quantum Alternating Operator Ansatz (QAOA+)**
> implemented with intersection-aware, multi-controlled bit-flip mixers. We
> execute the circuit on IBM's superconducting backends — `ibm_torino`,
> 133 qubits — and evaluate on Siemens's real-world instances with six
> trains over six stations. We benchmark against both classical Benders
> decomposition approaches and a fully centralised classical solver. We
> show that our method **converges in significantly fewer iterations than
> classical baselines, while still producing feasible timetables that
> preserve all safety margins** and operating within currently available
> quantum resources. The primary limitation remains the extended runtime
> on quantum hardware. Our findings highlight the need for further research
> into noise-resilient ansatz design and backend-specific compilation
> techniques to fully unlock the potential of quantum-hybrid decomposition
> methods for rail rescheduling in the NISQ era.

> *Heidtmann, Zubarev, Kratzer, Krüger, Poggi — "Quantum Benders
> Decomposition for Train Rescheduling Problems", LMU Munich, 2025.* See
> [`Siemens_Train_Rescheduling_Gate_Model_FINAL.pdf`](Siemens_Train_Rescheduling_Gate_Model_FINAL.pdf).

## Highlights

- 🧪 **Executed on real quantum hardware** — circuits transpiled and run on
  IBM Quantum's **`ibm_torino`** (Heron, 133-qubit) via the Qiskit Runtime
  `SamplerV2` primitive. Peak problem+ancilla usage in our experiments
  reached **~38 qubits** at the hardest difficulty level — comfortably
  inside the device's 133-qubit budget.
- 🚆 **Benchmarked on a Siemens-provided industrial dataset** — 19 TRP
  instances derived from a Norwegian regional network (**40 connector
  nodes, 47 track segments**), with **6 trains over 6 stations** per
  instance. Difficulty is parameterised by the *earliest access time*
  (`15:32:00 → 15:49:00`, 19 levels of increasing congestion).
- 📉 **Converges in significantly fewer Benders iterations** than the
  classical greedy / Gurobi set-cover masters, especially on the harder
  difficulty levels.
- ✅ **Near-optimal solution quality** — QAOA+ total deviation nearly
  coincides with the centralised Gurobi reference at low-to-medium
  difficulty and shows only marginal excess delay at the hardest levels.
- 🤝 **Industry × academia** — LMU Munich, Siemens AG, and QAR Lab
  contributed problem formulation, data, and quantum-algorithm engineering.

## Architecture

The framework decomposes the TRP into a **classical satisfiability
sub-problem** and a **quantum-assisted set-cover master problem**, exchanged
through Benders cuts.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                       Quantum-Hybrid Benders Loop                        │
│                                                                          │
│   Siemens timetable + network                                            │
│           │                                                              │
│           ▼                                                              │
│   ┌────────────────────────┐                                             │
│   │ io_utils / translator  │   builds (fixed, selectable, deviations)    │
│   └─────────────┬──────────┘                                             │
│                 │                                                        │
│                 ▼                                                        │
│   ┌────────────────────────┐  active deviation predicates  ┌──────────┐  │
│   │   Z3 SAT sub-problem   │ ─────────────────────────────►│  master  │  │
│   │ (bucketed deviations,  │                               │   SCP    │  │
│   │   unsat-core cuts)     │ ◄───── disabled predicates ───│ (greedy /│  │
│   └─────────────┬──────────┘                               │  gurobi /│  │
│                 │                                          │ quantum) │  │
│        SAT  ────┴───►  feasible timetable                  └────┬─────┘  │
│        UNSAT ──►  unsat-core ─► add cut to master               │        │
│                                                                 ▼        │
│                                                ┌─────────────────────┐   │
│                                                │  QAOA-style ansatz  │   │
│                                                │  (qasmsolver.py)    │   │
│                                                │  cost layer + MC    │   │
│                                                │  bit-flip mixer     │   │
│                                                └──────────┬──────────┘   │
│                                                           │              │
│                                            OpenQASM ──►  Qiskit Runtime  │
│                                                           │              │
│                                                  IBM Quantum backend     │
└──────────────────────────────────────────────────────────────────────────┘
```

The control loop is implemented in
[`qcedule/routing.py`](qcedule/routing.py) (`benders_algorithm`):

1. Build a `SatProblem` and an empty `Problem` (set-cover master).
2. Ask Z3 for a schedule under the currently active deviation predicates.
3. If SAT, return the schedule. If UNSAT, take the unsat-core and feed it to
   the master as a new cut.
4. The master returns the minimal set of deviation predicates to **disable**
   in the next round, and the loop repeats.

### Classical components

**Continuous timing sub-problem** —
[`qcedule/satsolving/z3wrapper.py`](qcedule/satsolving/z3wrapper.py).
For each train×station event the wrapper introduces a real-valued arrival
variable `t_(i,s)`. Fixed precedences `t_j − t_i ≥ τ` and selectable choices
`Or(And(...), …)` are encoded directly. Deviations from the published
timetable are encoded as **bucketed predicates**: at discretisation level
`level∈{0,…,k-1}` the predicate `p_(i,s,level)` implies that the deviation of
event `(i,s)` is below `level · d_max / k`. Z3 is asked to satisfy the
*active* predicates as **assumptions**, so an UNSAT response yields a
minimal unsat-core whose elements are exactly the deviation predicates that
must be relaxed — the natural ground set for the SCP master cut. An
auxiliary `Xor` constraint enforces *unambiguity*: for each train, exactly
one of the platforms in an ambiguous station group is actually used (`t≠0`).

**Master Set-Cover Problem** —
[`qcedule/setcovering/scpwrapper.py`](qcedule/setcovering/scpwrapper.py).
Each Benders cut is a row in a Boolean DataFrame whose columns are the
deviation predicates seen so far. A column "covers" a row if disabling that
predicate would relax the corresponding unsat-core. Solving the SCP yields
the minimal set of predicates to disable in the next Z3 call. Three solvers
are interchangeable behind the same interface
([`qcedule/setcovering/clsolver.py`](qcedule/setcovering/clsolver.py),
[`qcedule/setcovering/qasmsolver.py`](qcedule/setcovering/qasmsolver.py)):

- `greedy` — `SetCoverPy` greedy heuristic, fast but suboptimal.
- `gurobi` — exact ILP solution, used as the classical reference.
- `quantum` — the QAOA-variant detailed below.

**Centralised baseline** —
[`qcedule/centralized.py`](qcedule/centralized.py) reformulates the whole TRP
as a single Gurobi MILP minimising total deviation. It is the
"do-everything-at-once" reference that the decomposition is benchmarked
against.

### Quantum circuit

The quantum master is a **Quantum Alternating Operator Ansatz** — a QAOA
variant in the sense of Hadfield et al. — with a problem-tailored mixer that
preserves SCP feasibility. The circuit is constructed in PennyLane, exported
to OpenQASM 2, and executed through Qiskit Runtime on hardware
(`qcedule/setcovering/qasmsolver.py`,
[`qcedule/setcovering/qasmrun.py`](qcedule/setcovering/qasmrun.py)).

**Wire layout.** `init_wire_map` allocates one *subset* qubit per SCP column
and one *element* (ancilla) qubit per SCP row. The all-ones initial state is
prepared by `X` gates on every subset wire — this corresponds to "all
predicates disabled" and is *trivially* a cover of the empty constraint set,
making it a natural feasible warm-start for the mixer to walk from.

**Cost layer.** A diagonal `RZ(γ)` per subset wire penalises selecting more
columns, biasing the optimiser toward minimum covers (`cost_layer`).

**Intersection-aware multi-controlled bit-flip mixer**
(`mc_bitflip_mixer`, contributed by D. Kratzer). For each subset `c` the
mixer applies `RX(β)` on the qubit of `c`, *but only if* dropping `c` would
still leave every element of `c` covered by some neighbour in the
**constraint graph** — the graph in which subsets are nodes and edges
connect subsets whose Boolean column vectors share at least one element
(`constraint_graph`). The control logic is:

1. For every element `e ∈ c`, compute on an ancilla the disjunction "some
   neighbour of `c` containing `e` is currently selected" using a chain of
   `MultiControlledX` (`qOr`).
2. Apply `RX(β)` to the qubit of `c`, controlled by **all** element
   ancillas — i.e. flip `c` only if every element it contains is already
   covered by another selected subset.
3. Uncompute the ancillas with a mirrored chain.

The result is a non-trivial, *feasibility-preserving* mixer in the spirit of
Hadfield's QAOA+: amplitude only leaves states that are valid SCP covers,
which is critical on noisy hardware where the cost-Hamiltonian alone cannot
suppress infeasible bitstrings. A static rendering of the transpiled circuit
on an Eagle backend is checked in as
[`circ.png`](circ.png) (raw OpenQASM in [`circ`](circ)).

**Parameter optimisation.** `optimize_parameters` runs SciPy COBYLA on
`count_cost`, the average Hamming weight of the measured bitstrings — a
direct estimator of the SCP cost. The number of layers, shots, and
optimisation steps are exposed as keyword arguments to `benders_algorithm`.

**Decomposition for hardware.** Before transpilation we decompose to
`{RX, RY, RZ, CNOT, Toffoli, X}` via `pennylane.transforms.decompose`, which
keeps the gate count low enough for the IBM coupling map. Qiskit's preset
pass manager (level 1) then maps onto a real backend (`ibm_torino` is
hard-coded in `qasmrun.run_circ`; swap as needed).

## Repository structure

```
quantum-benders-train/
├── qcedule/                         # main Python package
│   ├── routing.py                   # Benders driver (benders_algorithm, central_algorithm)
│   ├── centralized.py               # Gurobi MILP baseline
│   ├── config.py / config.toml      # global constants
│   ├── circuit.py                   # PennyLane reference QAOA circuit (illustrative)
│   ├── mock_circuit.py              # smoke-test ansatz for hardware connectivity
│   ├── io_utils/
│   │   ├── file_parser.py           # network/train file reader
│   │   ├── trains.py                # Train / StopEntry data classes
│   │   ├── routing_areas.py         # k-edge-connected component decomposition
│   │   ├── paths.py                 # all-paths enumeration & area paths
│   │   ├── orderings.py             # head-on / overtaking conflict detection
│   │   ├── translator.py            # Siemens data → (fixed, selectable, deviations)
│   │   └── routes_generator.py      # synthetic linear-corridor instances
│   ├── satsolving/
│   │   └── z3wrapper.py             # SatProblem (bucketed deviations + unsat cores)
│   ├── setcovering/
│   │   ├── scpwrapper.py            # DataFrame SCP wrapper
│   │   ├── clsolver.py              # greedy + Gurobi solvers
│   │   ├── qasmsolver.py            # QAOA driver (PennyLane → OpenQASM)
│   │   ├── qasmrun.py               # Qiskit Runtime SamplerV2 execution
│   │   ├── fetch_result.py          # post-hoc job-result fetcher
│   │   ├── q_test.py                # hardware connectivity smoke test
│   │   ├── qcsolver.py              # deprecated PennyLane-direct path
│   │   └── qiskitsolver.py          # deprecated Qiskit-direct path
│   └── experiments/
│       ├── data.py                  # Result dataclass + pickle helpers
│       └── exp_framework.py         # run_benders_experiment, plot_metric, plot_qubits
├── data/                            # Siemens & toy network/train files
├── results/                         # pickled benchmark Result objects
├── logs/                            # transpiled model.lp, JSON dumps
├── tests/                           # unit tests (pytest / unittest)
├── notebooks/walkthrough.ipynb      # narrative walkthrough of the pipeline
├── modelling.ipynb                  # end-to-end demo notebook
├── plots.ipynb / plotting.ipynb     # figure generation
├── circ / circ.png                  # transpiled hardware circuit (qasm + image)
├── qubitsevolution.png              # qubit count vs. Benders iteration
├── pyproject.toml / requirements.txt
└── README.md
```

## Results

### Dataset

We benchmark on **19 TRP instances** derived from a Norwegian regional
network dataset provided by Siemens. Each instance corresponds to a
disruption scenario — e.g. a temporary network shutdown — characterised by
an **earliest access time** after which all trains may re-enter the
network.

- **Network topology:** 40 connector nodes, 47 track segments, each
  annotated with maximum speed and segment length
  (`data/network_OEOEB.txt`).
- **Train schedules:** 6 stations and 6 trains per instance, each defined
  by ordered stop events at specified stations
  (`data/train_OEOEB.txt`).
- **Difficulty knob:** earliest access time mapped to a difficulty level
  0–18. Later access times mean trains have less time to reach their first
  stops, so more conflicts are generated.

### Solver strategies compared

| Strategy | Role | Engine / parameters |
| --- | --- | --- |
| `centralized` | Reference: solves the *whole* TRP at once. | Gurobi 9.1 with continuous timing variables, deviation slacks, binary platform indicators, all precedence + unambiguity constraints. |
| `greedy`      | Benders master, classical heuristic. | `SetCoverPy` greedy column-selection — fastest but suboptimal. |
| `gurobi`      | Benders master, classical exact. | Gurobi 9.1 binary LP, `MIPGap=0`, no time limit — provably minimal cover. |
| `quantum` (QAOA+) | Benders master, quantum-hybrid. | PennyLane circuit (depth `p=2`), 2p `(γ, β)` parameters optimised by **COBYLA** with `maxiter=10` and `shots=10` per evaluation, transpiled at level 1, executed on **AerSimulator** *and* **`ibm_torino`** (`128` shots, up to 5 retries on transient runtime errors). |

The four pipelines share an identical SCP front-end: the same Z3 sub-
problem produces the same cuts, only the master changes. Raw `Result`
objects are pickled per constraint-difficulty bucket in `results/`; the
aggregate plots are produced by
`qcedule.experiments.exp_framework.plot_metric` and `plot_qubits` over
the metrics `time`, `iter_num`, `total_dev`, `rel_dev`, `max_qubits`.

### Reported metrics

- **Wall-clock runtime** — end-to-end time including master-loop solves
  and circuit execution. Hardware-queue delays are subtracted so that
  reported times reflect compute, not IBM scheduling latency.
- **Number of Benders iterations** — master-loop cycles until the Z3 sub-
  problem reports SAT.
- **Total deviation** — sum of train delays in the rescheduled timetable
  vs. the published one (seconds).
- **Maximum qubit usage** — peak (problem + ancilla) qubits in any
  single iteration.

### Headline findings

**1. Runtime — classical solvers are clearly faster on NISQ hardware.**
Classical runtimes grow predictably with difficulty (see `plots.ipynb`).
Greedy is the fastest at every level; Gurobi-master adds moderate cost;
the centralised Gurobi MILP exhibits the **highest** runtime at medium-to-
hard difficulty. Quantum runtimes are substantially higher: on the local
simulator, time grows sharply with circuit depth × shot count × COBYLA
iterations; on hardware, transpilation, network latency, and job
execution overhead dominate. **This is the primary current limitation of
the approach.**

**2. Solution quality — QAOA+ is on par with classical Benders.**
The centralised Gurobi solver provides the benchmark minimum deviation.
Both decomposed solvers (classical and quantum) show larger delays at the
hardest difficulties. **QAOA+ deviations nearly coincide with the
classical-Benders curves at low and medium difficulty, with only marginal
excess delay at the highest levels.** Schedules from every method respect
all precedence and unambiguity constraints — i.e. all returned timetables
are feasible and preserve safety margins.

**3. Iteration count — QAOA+ converges in significantly fewer Benders
rounds.** This is the headline algorithmic result. On the hardest
instances QAOA+ (both simulator and hardware) needs *far fewer* master-
loop iterations than the greedy or Gurobi master. The mechanism is
*counter-intuitive*: limited circuit depth (p=2), shot noise, and the
short COBYLA budget bias the QAOA+ output distribution toward selecting
**slightly larger relaxation sets** than strictly necessary. With more
constraints disabled per round, the SMT solver encounters fewer fresh
incompatibilities, so the decomposition terminates in fewer iterations.
Gurobi and greedy, in contrast, return tight (often minimal) covers, so
many constraints stay active, more conflicts surface, and cut generation
must repeat. As Leutwiler & Corman observed for railway timetabling [3],
*minimality of the master cover is not strongly correlated with schedule
quality* — even near-random or heuristic covers can yield similar total
deviations to an optimal cover.

**4. Qubit usage — well within current NISQ budgets.**

![Qubit count vs. Benders iteration](qubitsevolution.png)

Per-iteration qubit count is plotted in `qubitsevolution.png` for
difficulty levels 6, 9, 12, 15. As more conflicts are added, the SCP
gains rows (element ancillas) and possibly columns (subset qubits),
yielding a near-linear growth in total qubits over Benders iterations.
**Peak usage rises to about 38 qubits at difficulty level 15 — well below
the 133-qubit capacity of `ibm_torino`.** Allocating additional hardware
runtime would extend the experiments to even higher difficulties.

### Trade-off summary

| Metric | Centralised (Gurobi) | Greedy master | Gurobi master | QAOA+ master |
| --- | --- | --- | --- | --- |
| Solution quality (`total_dev`) | **best (reference)** | comparable | comparable | near-optimal, marginal excess at hardest levels |
| Wall-clock runtime | highest among classical | **fastest** | moderate | substantially higher (NISQ overhead) |
| Benders iterations | n/a (single solve) | high, grows with difficulty | high, grows with difficulty | **fewest** on hard instances |
| Peak qubits | n/a | n/a | n/a | up to ~38 (≤ 133-qubit budget) |
| Feasibility / safety | preserved | preserved | preserved | preserved |

The headline contribution is therefore not a wall-clock win — it is the
combination of **iteration efficiency** with **NISQ-feasible qubit
budgets** and **near-optimal solution quality**: as quantum hardware
matures and per-circuit overhead drops, the iteration-count advantage of
QAOA+ should translate into actual runtime gains, while the algorithmic
structure scales linearly in qubits with problem size.

## Installation

The project ships a `pyproject.toml` with `setuptools` packaging. The
recommended setup uses [uv](https://github.com/astral-sh/uv):

```bash
uv sync
```

This will create a `.venv/`, install all pinned dependencies from
`requirements.txt`, and install the local `qcedule` package in editable
mode. Manual `pip` works too:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

To run on real IBM hardware, copy the token template and fill in your IBM
Quantum API key:

```bash
cp .env.copy_and_fill_token .env
# then edit .env: QUANTUM_IBM_TOKEN=...
```

A simulator-only run does **not** require the token.

### Running the algorithm

```python
from qcedule.io_utils.file_parser import parse_network_file, parse_train_file
from qcedule.io_utils.translator import build_constraints
from qcedule.routing import benders_algorithm

trains = parse_train_file("data/train_OEOEB.txt")
G      = parse_network_file("data/network_OEOEB.txt")
constr = build_constraints(G, trains)

# `risks` enforces the unambiguity (Xor) constraints per train.
risks = {1: [[6, 21], [33, 0], [24, 7], [27, 14], [16, 30]],
         2: [[6, 21], [33, 0], [24, 7], [27, 14], [16, 30], [17]],
         # ...
         }

result = benders_algorithm(
    constr,
    platforms=risks,
    scp_strat="quantum",     # "greedy" | "gurobi" | "quantum"
    depth=2, steps=15, order=True,
)
print(result.iter_num, result.total_dev, result.max_qubits)
```

To reproduce the benchmarks, see
`qcedule.experiments.exp_framework.run_benders_experiment` /
`run_centralized_exp` and the `plots.ipynb` notebook.

## Hardware notes & limitations

- **Backends.** Hardware runs use **`ibm_torino`** (Heron, 133 qubits)
  through Qiskit Runtime; the code path also accepts any backend exposed
  by the user's IBM Quantum account. A `FakeBrisbane` noise model from
  `qiskit-ibm-runtime` is available for noisy-simulator experiments.
- **QAOA+ defaults.** `depth=2`, `shots=10` and `maxiter=10` for the
  COBYLA parameter optimiser, then `128` shots (with up to 5 retries on
  `RuntimeJobFailureError`) for the final hardware sample. These are the
  values used in the paper; they reflect a deliberate trade-off between
  per-iteration runtime and noise tolerance, not optimised hyper-
  parameters.
- **Qubit footprint.** One problem qubit per SCP subset plus one ancilla
  per conflict element. Peak observed usage was ~38 qubits at the hardest
  difficulty level — well under the 133-qubit ceiling. Larger instances
  would benefit from a more ancilla-frugal mixer Hamiltonian, an obvious
  next step.
- **Wall-clock.** End-to-end runtime is dominated by IBM queue waits and
  pass-manager transpilation, not gate execution. We subtract queue time
  from `Result.time` (`get_queuetime` in `routing.py`) so reported
  wall-clock numbers reflect compute, not scheduling latency. Even after
  this correction, quantum runtime is **much higher** than the classical
  baselines on every instance — the principal current limitation of the
  approach.
- **NISQ regime.** Physical hardware suffers from decoherence, read-out
  bias, and CNOT infidelity; for denser networks the required circuit
  depth may exceed the device's coherence window. AerSimulator runs are
  noise-free but exponentially slower than hardware on large instances.
- **Mixer cost.** The intersection-aware mixer uses ancillas plus
  `MultiControlledX` chains, which decompose into many CNOTs. We do *not*
  use `noancilla` MCX synthesis on the QAOA path; the trade-off is more
  qubits for shorter depth, which is the right call on Heron.

## References

The framework synthesises ideas from:

- J. F. Benders. *Partitioning procedures for solving mixed-variables
  programming problems* (1962). The decomposition principle.
- E. Farhi, J. Goldstone, S. Gutmann. *A Quantum Approximate Optimization
  Algorithm* (2014). The base QAOA algorithm.
- S. Hadfield et al. *From the Quantum Approximate Optimization Algorithm
  to a Quantum Alternating Operator Ansatz* (2019). The constraint-
  preserving mixer family that this work specialises to set cover.
- L. de Moura, N. Bjørner. *Z3: An efficient SMT solver* (2008). The
  underlying engine for the timing sub-problem and unsat-core extraction.
- IBM Quantum & Qiskit (Qiskit Runtime, `SamplerV2`, transpiler) — the
  hardware execution stack.

## Collaboration

Developed in collaboration with **Siemens AG** and the **QAR Lab** at LMU
Munich as part of the *Quantum Computing Practical* course at
**Ludwig-Maximilians-Universität München (LMU)**, summer term 2025.
Migrated from the LMU LRZ GitLab to GitHub for portfolio purposes.

**Authors.**

- Moritz Heidtmann — SCP wrapper, plotting, relative-delay metric.
- Andrei Zubarev — toy modelling, constraint construction (`translator.py`),
  QAOA framework, cost layer, hardware/simulator experiments.
- Daniel Kratzer — classical SCP solvers, centralised solver, intersection-
  aware multi-controlled bit-flip mixer, OpenQASM execution path, exact TRP
  modelling (orderings, paths, routing areas, trains), experiment & pickle
  infrastructure, repository management.
- Kilian Krüger — config plumbing, QAOA+ parameter optimisation, `Result`
  metrics.
- Emanuele Poggi — Z3 sub-problem (`z3wrapper.py`), IBM Runtime token
  handling, classical experiments.

## License

MIT — see [`LICENSE`](LICENSE) (to be added).
