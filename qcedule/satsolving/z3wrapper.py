# TODO: the "delta" variables can be deleted right? (in z3 objects)

# TODO: translator gives strings, not (int,int) tuples. But SatProblem expects tubles
#       I still need to check this...

# TODO: check/update doc strings, maybe are too verbose.

# TODO: pytest (coming soon)

"""z3wrapper.py – Z3 feasibility sub-problem for the Benders + SCP loop.

Each deviation constraint is guarded by its own Boolean predicate.
`solve()` passes *active* predicates as Z3 assumptions; on UNSAT
`solver.unsat_core()` directly yields the conflicting predicates, which
serve as “elements” for the set-cover master.

Example Benders loop::

    satp = SatProblem(fixed, selectables, deviations)
    scp  = scpwrapper.Problem()

    disabled: set[z3.BoolRef] = set()
    while True:
        sat, model, core = satp.solve(disabled=disabled)
        if sat:
            break                 # converged – use `model`
        scp.add(core)             # add new Benders cut
        disabled = scp.solve()    # predicates to remove next round
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

from z3 import (
    And,
    Bool,
    BoolRef,
    Implies,
    ModelRef,
    Or,
    Real,
    RealVal,
    Solver,
    Xor,
    sat,
    unsat,
)

from ..io_utils.translator import ORIGIN

# User-tuneable constants
DEFAULT_DMAX = 0  # global deviation budget (0 → disabled)
DEFAULT_K = 0  # #bucket levels  (0 → single-predicate formulation)


# Type aliases
Idx = Tuple[int, int]  # (train, station)
FixedBounds = Dict[Tuple[Idx, Idx], float]
SelectableBounds = Dict[int, Dict[int, Dict[Tuple[Idx, Idx], float]]]
DeviationBounds = Dict[Idx, float]


class EmptyCoreExecption(Exception):
    """Raised when Z3 returns UNSAT but the unsat-core is empty."""

    pass


# Main class
@dataclass
class SatProblem:
    """Single scheduling instance encoded as a Z3 model.

    Parameters
    ----------
    fixed
        Dict mapping a fixed precedence edge ``((i,s), (i,t))`` to its
        minimal running time (seconds).
    selectable
        Nested dict ``decision → choice → {edge: lb}`` implementing path
        alternatives or head-on conflicts.
    deviations
        Scheduled arrival offsets ``(i,s) → sched_sec``.
    d_max
        Global deviation budget in seconds.  ``0`` → no global budget.
    k
        Number of discretisation *steps* per event.
        *k = 0* → a **single** predicate per event
        *k > 0* → *k* bucket predicates plus one hard max-bucket.
    """

    fixed: FixedBounds
    selectable: SelectableBounds
    deviations: DeviationBounds
    d_max: float = DEFAULT_DMAX
    k: int = DEFAULT_K
    amb_risks: dict = field(default_factory=dict)

    # Z3 objects
    solver: Solver = field(init=False, default_factory=Solver)
    arrival: MutableMapping[Idx, Real] = field(init=False, default_factory=dict)
    delta: MutableMapping[Idx, Real] = field(init=False, default_factory=dict)
    predicates: MutableMapping[Idx, List[BoolRef]] = field(
        init=False, default_factory=dict
    )

    # Model construction
    def __post_init__(self) -> None:
        self._encode_fixed()
        self._encode_selectables()
        self._encode_deviations()  # handles both k=0 and k>0
        self._set_arrival_bounds()
        self._ensure_unambiguity()

    def _ensure_unambiguity(self):
        """Force exactly-one-platform usage per ambiguous OCP group.

        For each group of platforms a train could occupy, we add an n-ary
        XOR over ``arrival[(t,s)] != 0``. Z3 has no native n-ary XOR, so
        ``_mXor`` folds binary ``Xor`` to express it.
        """
        for t, ps in self.amb_risks.items():
            for p in ps:
                self.solver.add(self._mXor([self.arrival[(t, s)] != 0 for s in p]))

    def _mXor(self, args: list):
        """Right-fold a list of Boolean refs into a chain of binary XORs."""
        if not args:
            return False
        else:
            head, *tail = args
            return Xor(head, self._mXor(tail))

    # Encoding helpers
    # ----------------------------------------------------------------
    def _ensure_arrival(self, idx: Idx) -> None:
        """Declare ``t_idx`` if it does not exist."""
        if idx not in self.arrival:
            self.arrival[idx] = Real(f"t_{idx}")

    def _set_arrival_bounds(self):
        for idx in self.arrival:
            if idx == ORIGIN:
                self.solver.add(self.arrival[idx] == 0)
            else:
                self.solver.add(self.arrival[idx] >= 0)

    # Fixed precedences
    # ----------------------------------------------------------------
    def _encode_fixed(self) -> None:
        """Encode all fixed precedence constraints ``t_j − t_i ≥ lb``."""
        for (a, b), lb in self.fixed.items():
            self._ensure_arrival(a)
            self._ensure_arrival(b)
            self.solver.add(self.arrival[b] >= self.arrival[a] + RealVal(lb))

    # Selectable precedences
    # ----------------------------------------------------------------
    def _encode_selectables(self) -> None:
        """Encode all decision as ``Or(And(...), …)``"""
        for choices in self.selectable.values():
            choice_clauses = []
            for rels in choices.values():
                and_clause = []
                for (a, b), lb in rels.items():
                    self._ensure_arrival(a)
                    self._ensure_arrival(b)
                    and_clause.append(self.arrival[b] >= self.arrival[a] + RealVal(lb))
                choice_clauses.append(And(*and_clause))
            self.solver.add(Or(*choice_clauses))

    # Deviations: single predicate (k==0) or discretised (k>0)
    # ----------------------------------------------------------------
    def _encode_deviations(self) -> None:
        """Encode single-level or discretised deviation encoder."""
        if self.k <= 0:
            self._encode_single_level_deviations()
        else:
            self._encode_discretised_deviations()

    def _encode_single_level_deviations(self) -> None:
        for idx, sched in self.deviations.items():
            self._ensure_arrival(idx)
            t = self.arrival[idx]
            d_max = self.d_max
            self.solver.add(RealVal(d_max) - t >= RealVal(-1 * sched))

    def _encode_discretised_deviations(self) -> None:
        step = self.d_max / self.k
        for idx, sched in self.deviations.items():
            self._ensure_arrival(idx)
            t = self.arrival[idx]
            preds: List[BoolRef] = []
            for level in range(self.k):
                d = level * step
                p = Bool(f"(({idx[0]}, {idx[1]}), {level})")
                preds.append(p)
                self.solver.add(Implies(p, RealVal(d) - t >= RealVal(-1 * sched)))
            self.predicates[idx] = preds

            # Add deviation constraint as normal constraint, because this should always hold.
            d_max = self.k * step
            self.solver.add(RealVal(d_max) - t >= RealVal(-1 * sched))

    def core_by_index(self, core: list) -> list:
        """Convert Z3 unsat-core predicates back to their tuple indices.

        Predicates are named with their stringified ``((train, station),
        level)`` so ``eval`` round-trips that into a Python tuple, which
        is what the SCP master expects as a column label.
        """
        return [eval(str(p)) for p in core]

    # Solve
    def solve(
        self,
        *,
        disabled_from: Optional[Iterable[BoolRef]] = None,
    ) -> Tuple[bool, Dict[Idx, float], List[BoolRef]]:
        """Check feasibility under a given predicate *blacklist*.

        Parameters
        ----------
        disabled_from
            Iterable of predicates that must **not** be passed as assumptions
            (i.e. their associated deviation bucket is relaxed).  Pass
            ``None`` on the first iteration.

        Returns
        -------
        sat : bool
            True  → Z3 found a schedule;  False → UNSAT.
        model : Dict[(int,int), float]
            Arrival times if *sat* is True, else ``{}``.
        core  : List[z3.BoolRef]
            The unsat-core predicates if *sat* is False, else ``[]``.

        Raises
        ------
        EmptyCoreExecption
            If Z3 is UNSAT **and** the core is empty (no relaxable
            deviation constraints left).
        RuntimeError
            If Z3 answers *unknown* (timeout or numerics).
        """
        # build the assumption list
        assumptions = []
        for plist in self.predicates.values():
            # iterate list in reverse to exclude tighter bounds just by breaking the loop
            for p in plist[::-1]:
                if p in disabled_from:
                    # p in disabled_from -> do not include all predicates refering to a tighter bound
                    break
                assumptions.append(p)
        res = self.solver.check(*assumptions)
        if res == sat:
            return True, self._model_as_dict(self.solver.model()), []
        if res == unsat:
            core = list(p for p in assumptions if p in self.solver.unsat_core())
            if not core:
                # If there is a core with only non-tracked constraints,
                # the problem is not satisfiable by ignoring any tracked constraints.
                raise EmptyCoreExecption(
                    "SAT Problem returned unsat but unsat core is empty!"
                )
            return False, {}, core
        raise RuntimeError("Z3 returned *unknown* – consider a timeout.")

    # Helper.
    def _model_as_dict(self, m: ModelRef) -> Dict[Idx, float]:
        """Convert a Z3 model into ``{(train,station): arrival_sec}`."""
        result: Dict[Idx, float] = {}
        for idx, var in self.arrival.items():
            val = m[var]
            if val is None:
                continue
            num = val.numerator_as_long()
            den = val.denominator_as_long()
            result[idx] = num / den
        return result

    # External inspection for predicates
    @property
    def deviation_predicates(self) -> Mapping[Idx, List[BoolRef]]:
        """Return a read-only view of all deviation bucket predicates.
        Used by the master SCP module to know which literals it may disable
        in subsequent Benders iterations.
        """
        return self.predicates


# final wrapper
def build_sat_problem(
    fixed: FixedBounds,
    selectable: SelectableBounds,
    deviations: DeviationBounds,
    *,
    d_max: float = DEFAULT_DMAX,
    k: int = DEFAULT_K,
) -> SatProblem:
    """Helper for one‑liner construction (keeps callers tidy)."""
    return SatProblem(fixed, selectable, deviations, d_max=d_max, k=k)
