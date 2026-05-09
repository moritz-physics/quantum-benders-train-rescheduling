"""For parsing data files"""

from typing import Optional

from networkx import MultiGraph

from .trains import StopEntry, Train

IFOLDER = "data"
LFOLDER = "logs"
TRAINS = "train_easy.txt"
NET = "network_easy.txt"
OCP2P = {
    "ocp-175": [21, 6],
    "ocp-454": [0, 33],
    "ocp-646": [24, 7],
    "ocp-2": [27, 14],
    "ocp-265": [30, 16],
    "ocp-586": [17],
}


def parse_time(t: str) -> Optional[int]:
    """
    Parses a time string in format 'HH:MM:SS' and returns the number of seconds since midnight.

    Returns:
        int: number of seconds since 00:00:00
        None: if time is missing or malformed
    """
    if not t or t.strip() in {"N/A", "-", "", None}:
        return None
    try:
        h, m, s = map(int, t.strip().split(":"))
        return h * 3600 + m * 60 + s
    except Exception as e:
        print(f"[!] Can't parse time: {t.strip()} — {e}")
        return None


def parse_network_file(path):
    """
    Reading network_OEOEB.txt, getting data, building a graph
    """
    G = MultiGraph()
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("c"):
                parts = line.strip().split()
                _, seg_id, p_from, p_to, v_max, length = parts
                time_sec = float(length) / (
                    float(v_max) * 1000 / 3600
                )  # converting time to seconds
                G.add_edge(
                    int(p_from),
                    int(p_to),
                    key=int(seg_id),
                    time=round(time_sec, 2),
                    length=float(length),
                    vmax=float(v_max),
                )
    return G


def parse_train_file(path):
    """
    Reading train_OEOEB.txt, getting data, exctracting list of trains and their stops
    """
    trains = []
    current = None

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("Train ID:"):
                if current:
                    trains.append(current)
                current = Train()
            elif line.startswith("- OCP Ref:") and current is not None:
                parts = line.split(",")
                ocp = parts[0].split(":")[-1].strip()
                arr = parts[2].replace("Arrival:", "").replace(",", "").strip()
                dep = parts[3].replace("Departure:", "").replace(",", "").strip()
                arr = -1 if arr == "N/A" else parse_time(arr)
                dep = -1 if dep == "N/A" else parse_time(dep)
                stop = StopEntry(arrival=arr, departure=dep, ocp=OCP2P[ocp])
                current.add_stop(stop)
            elif line.startswith("="):
                if current:
                    trains.append(current)
                    current = None

    if current:
        trains.append(current)

    return trains
