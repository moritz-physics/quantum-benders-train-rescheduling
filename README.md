# Quantum Benders Decomposition for Train Rescheduling Problems (TRP)
This project is part of the Quantum Computing Practical course in held in summer 2025 at LMU.
## Description
This project implements a quantum hybrid approach for a Benders decomposition in the context of train rescheduling in the python package "qcedule". The Problem is devided in a subproblem solved with z3 and a Set Covering Problem (SCP) solved with the help of Quantum Computing. The package also offers pure classical solvers for both decomposed and centralized approaches.


## Usage
You can run the algorithm by importing the following and running:
```
from qcedule.routing import benders_algorithm

result = benders_algorithm(constr, platforms, scp_strat="quantum", **kwargs)
```
Here `constr` is a tuple of constraints describing a TRP. `platforms` should be a list of lists of segment ids of which you want an unambiguous solution for, i.e. for one train only one of the segments in a list should be scheduled (needed because of internals of z3). `scp_strat` can also be `"greedy"` and `"gurobi"` to use classical SCP solvers. You can pass additional arguments for the quantum part (layers, optimization steps, etc.) as keyword arguments.
The result is a `Result` object defined in `qcedule.experiments.data`.
You can also use our experimental framework:
```
from qcedule.experiments import run_benders_experiment, run_centralized_exp
```
They take dictionaries of constraint tupels and you can pass an additional `samples` argument which specifies how many runs to perform in one configuration.
`load_results` and `save_results` can be helpful to manage result storage in `pickle` files.
See ``.ipynb``-files for detailed usage.

## Experiments Data
We already conducted some experiments. As dataset we used the constraint dictionary stored in `constraints.pkl` which includes constraints for 19 different TRPs with increasing difficulty. It can be loaded with `qcedule.experiments.exp_framework.load_constraints`.
We stored our results in `pickle` files which are stored in the `results` folder.


## Author Contributions
Disclaimer: qasmsolver and qasmrun are built from copied snippets from the deprecated modules qcsolver and qiskitsolver. So most mentioned contributions to qasmsolver and qasmrun are also contributions to those deprecated modules.

Moritz Heidtmann:
- Implementation of SCP Problem (scpwrapper.py), plotting function (exp_framework.plot_metric), add_relative_delay function in experiments.data

Andrei Zubarev:
- Implementation of toy modelling example (routes_generator.py), constraint construction framework (translator.py), QAOA algorithm framework, general circuit, cost layer (qasmsolver.py), circuits for testing hardware connection (mock_circuit.py, circuit.py, setcovering.fetch_result, setcovering.q_test)
- Conducted quantum hardware and simulator experiments

Daniel Kratzer:
- Implementation of classical scp solvers (clsolver.py), centralized solver (centralized.py), mixer circuit (qasmsolver.mc_bitflip_mixer), qasm conversion and running (qasmrun.py), exact TRP modeling (orderings, paths, routing_areas and trains)
interface of SCP Problem (scpwrapper.py), experiment functions (run_benders_experiment, run_centralized_exp, plot_qubits), pickle file infrastructure (functions like load_results, save_results in experiments.data, load_constr, save_constr in experiments.exp_framework)
- Helped with constraint construction
- Repository management

Kilian Krüger:
- Implementation of config file (config.py), QAOA+ parameter optimization (qasmsolver.optimize_parameters), metrics measurement (class experiments.data.Result, building Result objects inside routing.benders_algorithm)

Emanuele Poggi:
- Implementation of subproblem (z3wrapper.py), connection to IBM service via tokens (e.g. in header of qasmrun.py).
- Conducted classical experiments.

## License
This project is not licensed yet.
