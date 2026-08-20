import json
from datetime import date, datetime
from json import JSONEncoder
from typing import Any
from uuid import UUID

from jinja2.utils import htmlsafe_json_dumps
from pydantic import BaseModel

from app.presenters.base import BasePresenter
from infra.db import GlobalID, RecordModel


class Encoder(JSONEncoder):
    def default(self, obj):
        match obj:
            case UUID() | GlobalID():
                return str(obj)
            case datetime() | date():
                return obj.isoformat()
            case BaseModel():
                return obj.model_dump()
            case BasePresenter() | RecordModel():
                return obj.dump([UUID, datetime, GlobalID])
        return JSONEncoder.default(self, obj)


def to_json(data: Any, **kwargs) -> str:
    def custom_dumps(obj: Any, **dump_kwargs) -> str:
        return json.dumps(obj, cls=Encoder, **{**kwargs, **dump_kwargs})

    return str(htmlsafe_json_dumps(data, dumps=custom_dumps))
