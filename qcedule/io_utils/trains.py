"""Implements train class"""

from bisect import insort
from dataclasses import dataclass, field


@dataclass(order=True)
class StopEntry:
    arrival: int = -1
    departure: int = -1
    ocp: list = field(default_factory=list)


@dataclass
class Train:
    stops: list[StopEntry] = field(default_factory=list)
    paths: list[list] = field(default_factory=list)
    idx: int = -1
    decisions: list[int] = field(default_factory=list)

    def add_stop(self, stop: StopEntry):
        insort(self.stops, stop)

    def get_ocps(self):
        return [s.ocp for s in self.stops]

    def __repr__(self):
        string = "OCPs:"
        for s in self.stops:
            line = f"\n\t- OCP Ref: {s.ocp}, Type: stop, Arrival: {s.arrival}, Departure: {s.departure},"
            string += line
        return string
