from typing import Any, TypeVar

from pydantic import BaseModel

from infra.db import RecordModel, dump_fields

T = TypeVar("T", bound=RecordModel | BaseModel)


class BasePresenter[T: RecordModel | BaseModel]:
    def __init__(self, model: T, **kwargs) -> None:
        self.model = model
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __str__(self) -> str:
        return str(self.model)

    def __getattr__(self, item: str) -> Any:
        try:
            return getattr(self.model, item)
        except AttributeError:
            raise AttributeError(f"{self.__class__.__name__} object has no attribute '{item}'")

    def dump(self, extra_allowed_classes: list[type] = []):
        if isinstance(self.model, BaseModel):
            results = self.model.model_dump()
        elif isinstance(self.model, RecordModel):
            results = self.model.dump(extra_allowed_classes)
        else:
            raise ValueError(f"Cannot dump unsupported model type: {type(self.model)}")

        for key, value in dump_fields(self).items():
            results[key] = value

        return results
