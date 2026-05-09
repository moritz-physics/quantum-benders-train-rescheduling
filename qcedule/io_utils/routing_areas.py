"""Algorithms to find routing areas."""

# Idea: - model multigraph as graph with auxiliary nodes and edges to model 2-cycles
#       - get all k-edge-connected components
#       - remove auxiliary nodes from components

import itertools as it

import networkx as nx
from matplotlib import pyplot as plt

from .file_parser import parse_network_file


class AuxNode:
    """Auxiliary nodes."""

    def __init__(self, id):
        self.id = id


def multi_k_edge_ccs(G: nx.MultiGraph, k: int = 1):
    """Implements nx.k_edge_components() for MultiGraphs."""

    # Initialize auxiliary graph as normal Graph.
    A = nx.Graph(G)
    # Find parallel edges in multigraph
    parallels = filter(
        lambda x: x[2] > 1, {(u, v, G.number_of_edges(u, v)) for u, v in A.edges}
    )
    # Add auxiliary nodes and edges to model parallel edges from multigraph
    aux_id = 0
    for u, v, n in parallels:
        for _ in range(n - 1):
            aux = AuxNode(aux_id)
            A.add_edges_from([(u, aux), (aux, v)])
            aux_id += 1
    # Get the k-edge-components
    components = nx.k_edge_components(A, k)
    # Filter out auxiliary nodes and yield components
    for c in components:
        yield set(filter(lambda x: not isinstance(x, AuxNode), c))


def find_areas(G: nx.MultiGraph) -> set[nx.MultiGraph]:
    """Find routing areas where trains can take different paths.

    Args:
        G (nx.MultiGraph): A network Graph.

    Returns:
        set[nx.MultiGraph]: Subgraphs representing routing areas.
    """
    areas = set()
    for c in multi_k_edge_ccs(G, k=2):
        # Add only multi-node components as an area
        if len(c) > 1:
            area = G.subgraph(c)
            areas |= {area}
    return areas


# This is for graphically displaying the network
def get_positions(path):
    """get graph vertex position"""
    pos = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("p"):
                parts = line.strip().split()
                _, p_id, x, y = parts
                pos[int(p_id)] = float(x), float(y)
    return pos


if __name__ == "__main__":
    # Little test, shows the routing areas
    path = "data/network_easy.txt"
    G1 = parse_network_file(path)
    pos = get_positions(path)
    areas = find_areas(G1)
    print(areas)
    connectionstyle = [f"arc3,rad={r}" for r in it.accumulate([0.15] * 4)]
    for G in areas:
        nx.draw_networkx(G, pos=pos, connectionstyle=connectionstyle)
    plt.show()
    nx.draw_networkx(G1, pos=pos, connectionstyle=connectionstyle)
    plt.show()
