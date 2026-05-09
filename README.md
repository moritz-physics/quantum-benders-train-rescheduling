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

Restoring a safe, minimal-delay railway timetable after a disruption is a
combinatorial optimisation problem that scales poorly with the number of
trains, stations and conflict points. This work presents a **quantum-hybrid
Benders decomposition** for the Train Rescheduling Problem (TRP) that
decouples the *continuous* problem of choosing arrival/departure times from
the *combinatorial* problem of choosing precedence and routing decisions.
The continuous timing sub-problem is encoded as a Z3 satisfiability instance
with bucketed deviation predicates, so that a minimal unsatisfiable core
yields a Benders feasibility cut. The combinatorial master problem becomes a
Set-Cover Problem (SCP) over those cuts and is solved on superconducting
quantum hardware with a Quantum Alternating Operator Ansatz (a QAOA variant)
whose mixer is built from intersection-aware multi-controlled bit-flips,
preserving the SCP feasible subspace. The framework was benchmarked on
real-world Siemens instances of six trains over six stations and converges in
significantly fewer Benders iterations than the classical SCP master
formulation while producing schedules that respect every safety margin.
Circuits up to **133 qubits** were executed on IBM Quantum backends.

## Highlights

- 🧪 **Executed on real quantum hardware** — circuits with up to **133
  qubits** transpiled and run on IBM superconducting backends (Eagle/Heron
  family) via the Qiskit Runtime `SamplerV2` primitive.
- 🚆 **Benchmarked on Siemens real-world instances** — six trains routed over
  six stations on a topology derived from a real corridor (network/train
  files in `data/`).
- 📉 **Outperforms classical Benders in iteration count** — the
  intersection-aware quantum master converges in fewer Benders rounds than
  the classical greedy / Gurobi set-cover masters on the same instances.
- ✅ **Feasible, safety-preserving timetables** — every returned schedule
  respects the head-on / overtaking precedence rules and ambiguity
  constraints that encode platform safety.
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

Benchmarks compare three pipelines on the Siemens 6-train / 6-station
instance, parameterised by an "earliest-time" knob (`15:32:00 … 15:50:00`)
that increasingly tightens the timetable:

- **`centralized`** — single Gurobi MILP over the full TRP.
- **`greedy` / `gurobi`** — Benders decomposition with a *classical* SCP
  master.
- **`quantum`** — Benders decomposition with the QAOA-variant SCP master.
- **`simulator`** — same QAOA master executed on the noiseless Aer
  simulator, for sanity-checking the hardware runs.

All raw `Result` objects are pickled in `results/` (one file per
constraint-difficulty bucket; see `plots.ipynb` for the loading pattern).
The aggregate plots are generated by
`qcedule.experiments.exp_framework.plot_metric` over the metrics
`time`, `iter_num`, `total_dev`, `rel_dev`, `max_qubits`.

![Qubit count vs. Benders iteration](qubitsevolution.png)

The figure above shows the qubit count required by the SCP master at each
Benders iteration, across the difficulty buckets that were actually run on
hardware. The qubit budget grows monotonically with the iteration index
(the SCP DataFrame gains a column per new cut), peaking at **133 qubits**
on the hardest instance — the ceiling of the Eagle generation.

Headline qualitative findings:

| Metric | Quantum-hybrid | Classical Benders | Centralised |
| --- | --- | --- | --- |
| Iterations to converge | **fewest** on the hardest instances | more iterations than quantum | n/a (single solve) |
| Total deviation `total_dev` | matches centralised within instance limits | matches centralised | optimal reference |
| Wall-clock time | dominated by IBM queue + transpile | seconds | seconds |
| Qubits used | up to **133** | n/a | n/a |
| Feasibility / safety margins | every returned schedule satisfies all precedence + ambiguity constraints | same | same |

The quantum master tends to "absorb" multiple cuts per iteration through
its intersection-aware mixer, which is the mechanism behind the iteration-
count win. Wall-clock time is *not* a competitive metric in the NISQ era
(queue + transpile dominate), and we do not claim it; the contribution is
the algorithmic structure and its empirical iteration-count advantage on
real industrial constraints.

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

- **Backends.** Hardware runs use `ibm_torino` (Heron family, 133 qubits)
  through Qiskit Runtime; the code path also accepts any backend exposed by
  the user's IBM Quantum account. A `FakeBrisbane` noise model from
  `qiskit-ibm-runtime` is available for noisy-simulator experiments.
- **NISQ regime.** Two-qubit-gate noise and limited connectivity mean the
  QAOA master is run with shallow depth (2 layers, 10 shots, 10 COBYLA
  steps in the default config). Increasing `depth` quickly inflates
  transpiled circuit size beyond what current backends can execute with
  useful fidelity.
- **Wall-clock.** End-to-end runtime is dominated by IBM queue waits and
  pass-manager transpilation, not gate execution. We subtract queue time
  from `Result.time` (`get_queuetime` in `routing.py`) so reported
  wall-clock numbers reflect compute, not scheduling latency.
- **Mixer cost.** The intersection-aware mixer uses ancillas plus
  `MultiControlledX` chains, which decompose into many CNOTs. We do *not*
  use `noancilla` MCX synthesis on the QAOA path; the trade-off is more
  qubits for shorter depth, which is the right call on Eagle/Heron.

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
