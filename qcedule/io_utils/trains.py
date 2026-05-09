"""Implements train class"""

from bisect import insort
from dataclasses import dataclass, field


@dataclass(order=True)
class StopEntry:
    """A single stop on a train's itinerary.

    ``arrival``/``departure`` are seconds since midnight (``-1`` if the
    train enters / leaves the corridor at this stop). ``ocp`` is the list
    of platform IDs that may serve this operational control point -- the
    Z3 model picks exactly one via the unambiguity (Xor) constraint.
    """
    arrival: int = -1
    departure: int = -1
    ocp: list = field(default_factory=list)


@dataclass
class Train:
    """A train: an ordered list of stops plus its possible paths through the network."""
    stops: list[StopEntry] = field(default_factory=list)
    paths: list[list] = field(default_factory=list)
    idx: int = -1
    decisions: list[int] = field(default_factory=list)

    def add_stop(self, stop: StopEntry):
        """Insert a stop while keeping the list sorted by arrival time."""
        insort(self.stops, stop)

    def get_ocps(self):
        """Return the list of OCP platform groups in itinerary order."""
        return [s.ocp for s in self.stops]

    def __repr__(self):
        string = "OCPs:"
        for s in self.stops:
            line = f"\n\t- OCP Ref: {s.ocp}, Type: stop, Arrival: {s.arrival}, Departure: {s.departure},"
            string += line
        return string
