"""Implements searching for needed oredering relations."""

from dataclasses import dataclass, field

from .paths import get_fixed_segments
from .trains import Train

Idx = tuple[int, int]
SelectableBounds = dict[int, dict[int, dict[tuple[Idx, Idx], float]]]


@dataclass
class ConflictInfo:
    """Detected ordering conflict between two trains on a shared segment.

    Carries the segment id, the two train indices, the segments each train
    enters next (so we can encode head/tail removal times), and flags
    indicating whether those segments are part of fixed or selectable
    routes (``in_sel_*`` / ``out_sel_*``).
    """
    segment: int
    id_a: int
    id_b: int
    edges_out_a: set[int] = field(default_factory=set)
    edges_out_b: set[int] = field(default_factory=set)
    in_sel_a: bool = True
    in_sel_b: bool = True
    out_sel_a: bool = True
    out_sel_b: bool = True


def is_in(ls: list, elem: tuple):
    """Test whether ``elem`` (an undirected edge tuple) appears in ``ls``.

    Returns ``(found, index)``; checks both edge orientations because the
    network is modelled as a MultiGraph (undirected). The third tuple
    component is the parallel-edge key, so we keep it fixed.
    """
    x, y, k = elem
    if (x, y, k) in ls:
        return True, ls.index((x, y, k))
    elif (y, x, k) in ls:
        return True, ls.index((y, x, k))
    else:
        return False, None


def get_edge(p, i):
    """Safe indexing into a path; returns None at the boundary."""
    try:
        return p[i]
    except IndexError:
        return None


def get_conflicts(A: Train, B: Train):
    """Find every shared segment between any path of A and any path of B.

    Returns a dict ``edge -> ConflictInfo`` aggregating, for each shared
    segment, whether it lies on a fixed or selectable portion of either
    train and what the follow-up segments are. The follow-up segments
    drive the ordering choice in ``set_fixed_obound``.
    """
    fixedA = get_fixed_segments(A.paths)
    fixedB = get_fixed_segments(B.paths)

    detected = {}
    for p in A.paths:
        for idxA, edge in enumerate(p):
            for q in B.paths:
                found, idxB = is_in(q, edge)
                if found:
                    # build new conflict object if not existing
                    if edge not in detected.keys():
                        detected[edge] = ConflictInfo(
                            id_a=A.idx, id_b=B.idx, segment=edge[2]
                        )
                    info: ConflictInfo = detected[edge]
                    # store if the conflicting segment is a fixed one for A or B
                    info.in_sel_a = not is_in(fixedA, edge)[0]
                    info.in_sel_b = not is_in(fixedB, edge)[0]
                    # get the edge following the conflict in the path.
                    followA = get_edge(p, idxA + 1)
                    if followA is None:
                        info.edges_out_a = {}
                    else:
                        info.out_sel_a = not is_in(fixedA, followA)[0]
                        info.edges_out_a.add(followA[2])
                    # Same for B:
                    followB = get_edge(q, idxB + 1)
                    if followB is None:
                        info.edges_out_b = {}
                    else:
                        info.out_sel_b = not is_in(fixedB, followB)[0]
                        info.edges_out_b.add(followB[2])
    return detected


def ordering_bound(
    A: Train,
    B: Train,
    sel: SelectableBounds,
    seg: int,
    outA: set[int],
    sel_out=False,
    sel_in=False,
    wait=0,
):
    """Build the per-choice precedence bounds for "A leaves before B enters".

    ``sel_in`` / ``sel_out`` flags indicate whether the conflict segment
    or A's follow-up are inside a selectable routing choice -- in those
    cases we synthesise virtual indices and patch the affected choice
    dictionaries so the bound is conditional on the right route choice.
    ``wait`` is the head/tail removal time (0 if A continues with another
    segment immediately).
    """
    choicedict = {}

    # Find all possible indexes for second event (B on conflict seg)
    indeces2 = []
    if not sel_in:
        indeces2.append((B.idx, seg))
    else:
        # every time seg is discovered in a choice add an index and a relation to the choice
        for dec in B.decisions:
            for choice in sel[dec]:
                for (tid1, seg1), (tid2, seg2) in sel[dec][choice]:
                    if tid1 < 0 or tid2 < 0:
                        continue
                    if seg1 == seg or seg2 == seg:
                        i = (-B.idx, (seg, (dec, choice)))
                        indeces2.append(i)
                        new = {(i, (B.idx, seg)): 0}
                        sel[dec][choice].update(new)
                        break

    # Find all possible indexes for first event (A on seg after conflict)
    indeces1 = []
    if not sel_out:
        assert len(outA) == 1, (
            f"length was {len(outA)} not 1 for outA = {outA}, {sel_out}"
        )
        indeces1.append((A.idx, outA.pop()))
    elif not outA:
        for dec in A.decisions:
            for choice in sel[dec]:
                for (tid1, seg1), (tid2, seg2) in sel[dec][choice]:
                    if tid1 < 0 or tid2 < 0:
                        continue
                    if seg1 == seg or seg2 == seg:
                        i = (-A.idx, (seg, (dec, choice)))
                        indeces1.append(i)
                        new = {(i, (A.idx, seg)): 0}
                        sel[dec][choice].update(new)
                        break
    else:
        for dec in A.decisions:
            for choice in sel[dec]:
                for (tid1, seg1), (tid2, seg2) in sel[dec][choice]:
                    if tid1 < 0 or tid2 < 0:
                        continue
                    if seg1 in outA:
                        i = (-A.idx, (seg1, (dec, choice)))
                        indeces1.append(i)
                        new = {(i, (A.idx, seg1)): 0}
                        sel[dec][choice].update(new)
                        break
                    elif seg2 in outA:
                        i = (-A.idx, (seg2, (dec, choice)))
                        indeces1.append(i)
                        new = {(i, (A.idx, seg2)): 0}
                        sel[dec][choice].update(new)
                        break

    indeces = [(x, y) for x in indeces1 for y in indeces2]
    for index in indeces:
        choicedict[index] = wait
    return choicedict
