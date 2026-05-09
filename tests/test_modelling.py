import json

from qcedule.centralized import CentralSolver
from qcedule.io_utils.file_parser import LFOLDER, parse_network_file, parse_train_file
from qcedule.io_utils.orderings import get_conflicts
from qcedule.io_utils.paths import (
    get_area_paths,
    get_fixed_segments,
    get_selectable_seg_rel,
    train_paths,
)
from qcedule.io_utils.translator import build_constraints

net = "data/network_easy.txt"
trains = "data/train_easy.txt"
ts = parse_train_file(trains)
G = parse_network_file(net)


# def test_path():
#     for t in ts:
#         fixedsegs = get_fixed_segments(t, G)
#         borders = get_area_paths(t, G)

#         print(fixedsegs)
#         print(borders)
#         print(len(get_fixed_seg_rel(t, G)))
#         dummy = get_selectable_seg_rel(t, G)
#         print(dummy)


def test_constr():
    for t in ts:
        print(t)
    fixed, selectables, deviations = build_constraints(G, ts)

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


OCP2P = {
    "ocp-175": [21, 6],
    "ocp-454": [0, 33],
    "ocp-646": [24, 7],
    "ocp-2": [27, 14],
    "ocp-265": [30, 16],
    "ocp-586": [17, 2],
}
PLATFORMS = [21, 6, 0, 33, 24, 7, 27, 14, 30, 16, 17, 2]


def test_model():
    constr = build_constraints(G, ts)

    t = CentralSolver(constr)
    res, dev = t.solve()

    for item in res.items():
        if item[0][1] in PLATFORMS:
            print(item)
    print("Total deviation: ", dev)


def test_paths():
    paths = train_paths(ts[0], G)
    for p in paths:
        print(p)
    fixed = get_fixed_segments(paths)
    print(fixed)
    apaths = get_area_paths(paths, G)
    print(apaths)
    rel = get_selectable_seg_rel(paths, G)
    print("\n", rel)


def test_conflicts():
    for i, t in enumerate(ts, start=1):
        paths = train_paths(t, G)
        t.paths = paths
        t.idx = i
    a = ts[0]
    b = ts[1]
    conf = get_conflicts(a, b)
    for c in conf:
        print(c, conf[c])
