import functools
from datetime import date, datetime, time
from json import JSONDecoder, JSONEncoder
from json import dumps as json_dumps
from json import loads as json_loads
from uuid import UUID


class Encoder(JSONEncoder):
    def default(self, obj):
        match obj:
            case UUID():
                return {"__uuid__": True, "value": str(obj)}
            case datetime():
                return {"__datetime__": True, "value": obj.isoformat()}
            case date():
                return {"__date__": True, "value": obj.isoformat()}
            case time():
                return {"__time__": True, "value": obj.isoformat()}
            case set():
                return {"__set__": True, "value": list(obj)}
        return JSONEncoder.default(self, obj)


class Decoder(JSONDecoder):
    def __init__(self):
        JSONDecoder.__init__(self, object_hook=self.object_hook)

    def object_hook(self, obj):
        match obj:
            case {"__uuid__": True, "value": value}:
                return UUID(value)
            case {"__datetime__": True, "value": value}:
                return datetime.fromisoformat(value)
            case {"__date__": True, "value": value}:
                return date.fromisoformat(value)
            case {"__time__": True, "value": value}:
                return time.fromisoformat(value)
            case {"__set__": True, "value": value}:
                return set(value)
        return obj


JSONDumps = functools.partial(json_dumps, separators=(",", ":"), cls=Encoder)
JSONLoads = functools.partial(json_loads, cls=Decoder)
