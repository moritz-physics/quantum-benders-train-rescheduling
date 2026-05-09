"""Finding paths for trains."""

import operator

import networkx as nx

from .routing_areas import find_areas
from .trains import Train

T0 = (-1, -1, -1)


def covers(req: list[list[int]], path: list[tuple[int]]) -> bool:
    "Checks if path covers all required edges"
    seg_ids = [k for _, _, k in path]
    return all(any(p in seg_ids for p in ocp) for ocp in req)


def ordered(req: list[list[int]], path: list[tuple[int]]) -> bool:
    """Checks if path visits required segments in the right order."""
    r_seg = [k for _, _, k in path if any(k in ocp for ocp in req)]
    return all(s in r for r, s in zip(req, r_seg))


def flatten_mapping(mapping: dict[int, dict]):
    """Flatten a 2-level nested dict into a dict keyed by ``(outer, inner)``."""
    ret = {}
    for x, d in mapping.items():
        for y, val in d.items():
            ret[(x, y)] = val
    return ret


def farthest_nodes(G: nx.MultiGraph) -> tuple:
    """Return the pair of nodes with maximum shortest-path distance in ``G``.

    Used as the canonical entry / exit pair for trains traversing the
    corridor; trains then enumerate all simple paths between these two.
    """
    p = dict(nx.all_pairs_shortest_path_length(G))
    q = flatten_mapping(p)
    return max(q.items(), key=operator.itemgetter(1))[0]


def cut_path(path: list, edges, tail=False):
    """Trim a path until it starts (or, with ``tail=True``, ends) on ``edges``.

    Used to clip path enumerations for trains that enter or leave the
    corridor mid-route (``arrival/departure == -1``).
    """
    piter = path[::-1] if tail else path.copy()
    for edge in piter:
        if edge[2] in edges:
            break
        path.remove(edge)
    pass


def train_paths(train: Train, G: nx.MultiGraph):
    "Searches for all possible paths a train can take."
    req_platforms = train.get_ocps()
    # Take the two farthest points in the network as entry and exit
    entry, exit = farthest_nodes(G)
    all_paths = nx.all_simple_edge_paths(G, entry, exit)
    # Delete all paths that do not cover all required stations
    valid_paths = [p for p in all_paths if covers(req_platforms, p)]
    for p in valid_paths:
        # Some trains traverse the netwerk in reverse so we have to reorder the paths there
        if not ordered(req_platforms, p):
            p.reverse()
        if train.stops[0].arrival < 0:
            cut_path(p, req_platforms[0])
        if train.stops[-1].departure < 0:
            cut_path(p, req_platforms[-1], tail=True)
    return valid_paths


def order_segments(segs, path):
    """Order list of segments by the order they are visited in a path."""
    ordered_segs = []
    for e in path:
        for s in segs:
            if s == e:
                ordered_segs.append(s)
    return ordered_segs


def get_fixed_segments(paths):
    """Get segments that occur in all possible paths a train can take."""
    fsegs = []
    # Every path contains every fixed segment so we can take an arbitrary path to iterate through,
    # without missing any fixed segments
    p0 = paths[0]
    for e in p0:
        # Check if a segment is in all the other paths, too
        if all(e in p for p in paths):
            fsegs.append(e)
    # Somehow, ordering can get messed up, so we reorder here.
    return order_segments(fsegs, paths[0])


def get_area_paths(paths, network: nx.MultiGraph):
    """Get all paths for each routing area. Returns dictionary of the following structure:
    {(area_entry_node, area_exit_node): [path1, path2, ...]}
    """
    retpaths = {}
    # Iterate through the routing areas
    idx = 0
    for G in find_areas(network):
        choice = set()
        for p in paths:
            areapath = []
            begin = []
            # Keep track of wether the area is actually visited or not
            for e in p:
                # If edge in path is in area, add it to the current area path
                if e in G.edges:
                    areapath.append(e)
                # Append the first seg after area and break the loop if we left the area in the path
                elif areapath:
                    areapath.append(e)
                    break
                else:
                    # In this case we did not yet visited the area in the path
                    # -> add current edge as potential segment before area.
                    begin = [e]
            choice.add(tuple(begin + areapath))
        if len(choice) > 1:
            retpaths[idx] = choice
        idx += 1
    return retpaths


def get_fixed_seg_rel(paths):
    """Produces relations of which fixed segment comes before another for a train traveling a network"""
    # First, get the fixed segments
    fixed = get_fixed_segments(paths)
    rel = set()
    if fixed[0] == paths[0][0]:
        rel.add((T0, fixed[0]))
    # We iterate over sequential pairs of fixed segments
    for (x1, x2, x3), (y1, y2, y3) in zip(fixed, fixed[1:]):
        # If a pair of segments are sharing nodes, we know one preceeds the other
        if len(set([x1, x2, y1, y2])) < 4:
            # in this case we need a prec relation
            rel.add(((x1, x2, x3), (y1, y2, y3)))
    return rel


def get_selectable_seg_rel(paths, network: nx.MultiGraph):
    """Produces relations stored in a dict structure to model decisions and choices:
    {d_id: {c_id: [rel1, rel2, ...]}}
    with d_id has entry and exit of routing area as value and c_id has the actual route as value."""
    # First get all the area paths
    apaths = get_area_paths(paths, network)
    decisions = {}
    # Iterate over the areas, we have to make a decision for
    for d, ps in apaths.items():
        # Get edges/segments before and after routing area
        choices = {}
        # Now iterate over all possible paths. for each path we want to setup a set of prec relation
        for p in ps:
            # Each path resembles a choice and is indexed by the visited segments
            c_id = tuple(k for _, _, k in p)

            choice_rels = [r for r in zip(p, p[1:])]
            choices[c_id] = choice_rels
            for path in paths:
                if path[0] == p[0]:
                    choices[c_id].append((T0, p[0]))
        decisions[d] = choices
    return decisions
