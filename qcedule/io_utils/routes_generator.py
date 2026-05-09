import json
from itertools import permutations

import networkx as nx

from ..config import CONSTANTS


def generate_linear_routes(
    num_trains, num_stations, travel_time, deadline=None, return_graph=False
):  # deadline is currently unused, but can be useful in the future, return_graph is currently disable to not to mess with SAT-module
    """
    Generates a simple model of train routes:
    - each train travelling in a straight line through all stations
    - fixed time for each section (yet)
    - trains cannot be on the same section at the same time (selectables)
    - all trains have a deadline for arrival at the last station

    returns:
    - fixed precedence constraints,
    - selectable constraints,
    - deviation constraints,
    - a NetworkX graph of the network
    """

    fixed_prec = {}  # ((train, station), (train, next_station)) → travel_time
    selectables = {}  # decision_id → choice_id → constraint
    deviations = {}  # (train, station) → time constraint

    G = nx.DiGraph()  # a NetworkX graph

    #  Fixed precedence: each train goes through the stations in order.
    #  Example of result: "((0, 0), (0, 1))": XXX - "Train 0 goes from station 0 to station 1 no later then in XXX seconds"
    for train in range(num_trains):
        for station in range(num_stations - 1):
            key = ((train, station), (train, station + 1))
            fixed_prec[key] = travel_time
            G.add_edge((train, station), (train, station + 1), travel_time=travel_time)

    #  Selectables: trains cannot be on the same section of track at the same time. So we have to choose
    #  Example of result:
    # "0": { "((0, 1), (1, 1))": XXX }, - "Train 0 goes from station 0 to station 1 no later then in XXX seconds" OR
    # "1": { "((1, 1), (0, 1))": XXX } -  "Train 1 goes from station 0 to station 1 no later then in XXX seconds"

    # creates one decision_idx per station (in this case just station);
    # each choice contains the entire order of all trains, expressed through several constraints;
    # scales to an arbitrary number of trains: 2 → 2!, 3 → 6 orders, 4 → 24, etc.

    for station in range(1, num_stations):
        decision = {}
        all_orders = list(permutations(range(num_trains)))
        for choice_idx, order in enumerate(all_orders):
            precedence_set = {}
            for i in range(len(order) - 1):
                a = order[i]
                b = order[i + 1]
                precedence_set[((a, station), (b, station))] = travel_time
            decision[choice_idx] = precedence_set
        selectables[station] = decision

    #  Deviations: arrival at start position at 0, at final destination — no later then deadline
    #  Example of result:   "(0, 0)": 0,  - "Train 0 must be at station 0 no later than 0 seconds from the starting point (i.e. starts at 0)"
    #                       "(0, 1)": -6000 - "Train 0 must be at station 1 before 6000 seconds pass (minus in the model means: ≤ deadline)."
    #  For now we apply it only for final destination, later, I guess it should be independent for each (critical) station

    for train in range(num_trains):
        for station in range(num_stations):
            latest_arrival = travel_time * station
            deviations[(train, station)] = latest_arrival
    if return_graph:  # if we need data in Networkx format
        return (
            fixed_prec,
            selectables,
            deviations,
            G,
        )  # G is our NetworkX graph of the network
    return fixed_prec, selectables, deviations


# JSON does not support tuple keys, so recursively cast them to strings.
def stringify_keys(d):
    """Recursively convert dict tuple-keys to strings for JSON serialisation."""
    if isinstance(d, dict):
        return {str(k): stringify_keys(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [stringify_keys(i) for i in d]
    else:
        return d


# === Generating our model ===
# Generate_linear_routes(<number of trains>, <number of stations>, <each segment travel time in secs>, <CURRENTLY UNUSED! deadline in seconds CURRENTLY UNUSED!>)
# For now deadline is different for each station. Based on segment travel time. Can be fully individual for each station in the future.

num_trains_var = CONSTANTS["num_trains"]
num_stations_var = CONSTANTS["num_stations"]
travel_time_var = CONSTANTS["travel_time"]

print(
    f"Generating routes for {num_trains_var} trains, {num_stations_var} stations, each segment travel time {travel_time_var} seconds."
)

fixed, selectables, deviations = generate_linear_routes(
    num_trains_var, num_stations_var, travel_time_var
)  # example values, change them according your task  === ADD route_graph as variable AND return_graph=True in brackets for networkx ===)

# Combining and saving it
output = {"fixed": fixed, "selectables": selectables, "deviations": deviations}

with open(
    "linear_routes_model.json", "w", encoding="utf-8"
) as f:  # importing our model to linear_routes_model.json
    json.dump(stringify_keys(output), f, indent=2)

# Optional: for development/debugging — draw the graph (commented out for now)
# import matplotlib.pyplot as plt
# nx.draw(route_graph, with_labels=True, node_size=700)
# plt.show()
