import json
import os
from itertools import combinations

from networkx import MultiGraph

from ..config import CONSTANTS
from .file_parser import (
    IFOLDER,
    LFOLDER,
    NET,
    TRAINS,
    parse_network_file,
    parse_time,
    parse_train_file,
)
from .orderings import ConflictInfo, get_conflicts, ordering_bound
from .paths import T0, get_fixed_seg_rel, get_selectable_seg_rel, train_paths
from .trains import Train

T_REMOVAL = CONSTANTS["REMOVALTIME"]
F0 = 1000
EARLY = parse_time(CONSTANTS["EARLY"])
ORIGIN = (-1, -1)


def set_fbounds(
    fprecs: list[tuple[tuple[int]]], t_id: int, network: MultiGraph
) -> dict[tuple[tuple[int]], int]:
    """Sets bounds for relations between fixed segments, i.e. minimal travel time.

    Args:
        fprecs (list[tuple[tuple[int]]]): Precedence relations of MultiGRaph edges.
        train (int): The train ID.

    Returns:
        dict[tuple[int], int]: Storage of bounds. {(seg_id1, t_id),(seg_id2, t_id): bound}
    """
    fbounds = {}
    for (x, y, k1), (_, _, k2) in fprecs:
        # Set minimal travel time as bound value
        if (x, y, k1) == T0:
            fbounds[(ORIGIN, (t_id, k2))] = EARLY
            continue
        min_time = network.edges[x, y, k1]["time"]
        fbounds[((t_id, k1), (t_id, k2))] = min_time
    return fbounds


def set_dbounds(train: Train, t_id):
    dbounds = {}
    for stop in train.stops:
        arr = stop.arrival
        dep = stop.departure
        latest = max(dep, arr)
        for platform in stop.ocp:
            dbounds[(t_id, platform)] = latest
    return dbounds


def set_sbounds(
    choices: dict[tuple, set[tuple]], t_id: int, network: MultiGraph
) -> dict:
    """Adds bounds to selectable prec relations in choice set.

    Args:
        choices (dict[tuple, set[tuple]]): Stores the selectable prec relations per choice set.
        t_id (int): The trains id.
        network (MultiGraph): The network Graph.

    Returns:
        dict: Stores the bounds per selectable precedence realtion per choice set.
    """
    cdict = {}
    for c_id, choice in enumerate(choices):
        sbounds = {}
        for (x, y, k1), (_, _, k2) in choices[choice]:
            if (x, y, k1) == T0:
                sbounds[(ORIGIN, (t_id, k2))] = EARLY
                continue
            min_time = network.edges[x, y, k1]["time"]
            sbounds[((t_id, k1), (t_id, k2))] = min_time
        cdict[c_id] = sbounds

    return cdict


def set_fixed_obound(info: ConflictInfo, A: Train, B: Train, selectables: dict):
    cdict = {}
    # As 1st train enters seg after conflict, 2nd train can arrive -> difference 0:
    min_time0 = 0
    min_time1 = 0

    # Setting the relations:
    if not info.edges_out_a:
        # Case: no follow up -> wait for time HOLD after A entered seg k
        min_time0 = T_REMOVAL

    cdict[0] = ordering_bound(
        A,
        B,
        selectables,
        info.segment,
        info.edges_out_a,
        sel_out=info.out_sel_a,
        sel_in=info.in_sel_b,
        wait=min_time0,
    )
    # And again for other choice:
    if not info.edges_out_b:
        min_time1 = T_REMOVAL

    cdict[1] = ordering_bound(
        B,
        A,
        selectables,
        info.segment,
        info.edges_out_b,
        sel_out=info.out_sel_b,
        sel_in=info.in_sel_a,
        wait=min_time1,
    )
    return cdict


def build_constraints(G, trains: list[Train], ignore_order=False, early=EARLY):
    """
    Gather the constraints together
    """
    fixed = {}
    selectables = {}
    deviations = {}
    dec_id = 0
    global EARLY
    EARLY = early

    # For each train add minimal travel time bounds and deviations
    for t_idx, train in enumerate(trains, start=1):
        paths = train_paths(train, G)

        # deviation:
        deviations.update(set_dbounds(train, t_idx))

        # fixed: bounds for modeling minimal travel time outside routing areas
        fprec_relations = get_fixed_seg_rel(paths)
        fixed.update(set_fbounds(fprec_relations, t_idx, G))

        # selectable: bounds for modeling minimal travel time inside routing areas
        sprec_relations = get_selectable_seg_rel(paths, G)
        for dec in sprec_relations:
            choices = set_sbounds(sprec_relations[dec], t_idx, G)
            selectables[dec_id] = choices
            train.decisions.append(dec_id)
            dec_id += 1
        # Store paths for future computations
        train.paths = paths
        train.idx = t_idx

    # Now Find ordering restrictions/conflicts and add them as selectables
    # ToDo
    if ignore_order:
        return fixed, selectables, deviations

    for trainA, trainB in combinations(trains, 2):
        conflicts = get_conflicts(trainA, trainB)
        for info in conflicts.values():
            choices = set_fixed_obound(info, trainA, trainB, selectables)
            selectables[dec_id] = choices
            dec_id += 1

    return fixed, selectables, deviations


def total_dev(constr: tuple[dict], model):
    """Compute total deviation for a constraintset and a given model."""
    devs = constr[2]
    dev_values = []
    for idx, bound in devs.items():
        mtime = model[idx]
        if mtime > bound:
            dev_values.append(mtime - bound)
    return sum(d for d in dev_values)


def constraints_from_file():
    base = os.path.dirname(__file__)
    net_file = os.path.join(base, "../../", IFOLDER, NET)
    train_file = os.path.join(base, "../../", IFOLDER, TRAINS)

    G = parse_network_file(net_file)  # graph in Networkx format
    trains = parse_train_file(train_file)
    return build_constraints(G, trains)


if __name__ == "__main__":
    base = os.path.dirname(__file__)
    net_file = os.path.join(base, "../../", IFOLDER, NET)
    train_file = os.path.join(base, "../../", IFOLDER, TRAINS)

    G = parse_network_file(net_file)  # graph in Networkx format
    trains = parse_train_file(train_file)
    fixed, selectables, deviations = build_constraints(G, trains)

    # Saving to JSON for logging/debugging
    output = {
        "fixed": {str(k): v for k, v in fixed.items()},
        "selectables": {
            str(k): {str(i): {str(p): v for p, v in d.items()} for i, d in v.items()}
            for k, v in selectables.items()
        },
        "deviations": {str(k): v for k, v in deviations.items()},
    }
    with open(LFOLDER + "/industrial_constraints.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
