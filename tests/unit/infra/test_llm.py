from anthropic import NOT_GIVEN
from pydantic import BaseModel, Field

from infra.llm import _resolve_temperature, _unwrap_self_nested_list_fields


class _ListModel(BaseModel):
    items: list[str] = Field(default_factory=list)


class _DictModel(BaseModel):
    data: dict[str, list[str]] = Field(default_factory=dict)


def test_unwrap_repairs_self_nested_dict():
    model = _ListModel.model_construct(items={"items": ["a", "b"]})  # type: ignore[arg-type]

    _unwrap_self_nested_list_fields(model, ["items"])

    assert model.items == ["a", "b"]


def test_unwrap_is_noop_on_correct_shape():
    model = _ListModel.model_construct(items=["a"])

    _unwrap_self_nested_list_fields(model, ["items"])

    assert model.items == ["a"]


def test_unwrap_is_noop_on_wrong_key_name():
    payload = {"other": ["a"]}
    model = _ListModel.model_construct(items=payload)  # type: ignore[arg-type]

    _unwrap_self_nested_list_fields(model, ["items"])

    assert model.items == payload


def test_unwrap_is_noop_when_inner_is_not_a_list():
    payload = {"items": "not-a-list"}
    model = _ListModel.model_construct(items=payload)  # type: ignore[arg-type]

    _unwrap_self_nested_list_fields(model, ["items"])

    assert model.items == payload


def test_unwrap_only_touches_listed_fields():
    payload = {"data": ["bar"]}
    model = _DictModel.model_construct(data=payload)

    _unwrap_self_nested_list_fields(model, [])

    assert model.data == payload


def test_resolve_temperature_keeps_zero():
    # Regression: 0.0 is falsy, so `temperature or NOT_GIVEN` dropped it and the
    # API silently used its default. An explicit 0.0 must reach the request.
    assert _resolve_temperature(0.0) == 0.0


def test_resolve_temperature_passes_through_nonzero():
    assert _resolve_temperature(0.7) == 0.7


def test_resolve_temperature_none_is_not_given():
    assert _resolve_temperature(None) is NOT_GIVEN
