from datetime import date, datetime, time
from uuid import uuid4

from lib.json import JSONDumps, JSONLoads


def test_round_trips_supported_types():
    value = {
        "uuid": uuid4(),
        "datetime": datetime(2026, 5, 18, 9, 0),
        "date": date(2026, 5, 18),
        "time": time(9, 0),
        "set": {1, 2, 3},
    }
    assert JSONLoads(JSONDumps(value)) == value
