import json

import pytest
from pydantic import BaseModel
from tortoise import fields

from app.helpers.json import to_json
from app.presenters.base import BasePresenter
from infra.db import RecordModel
from tests.helpers.db import setup_in_memory_db  # noqa: F401


class PersonModel(RecordModel):
    name = fields.CharField(max_length=255, null=True)
    age = fields.IntField(null=True)


@pytest.mark.asyncio
async def test_model_dumping(setup_in_memory_db):  # noqa: F811
    await setup_in_memory_db(["tests.unit.helpers.test_json"])

    model = PersonModel(name="John", age=30)
    await model.save()
    result = to_json(model)
    parsed_result = json.loads(result)

    # TestModel fields
    assert parsed_result["name"] == "John"
    assert parsed_result["age"] == 30

    # RecordModel fields
    assert parsed_result["created_at"] is not None
    assert parsed_result["updated_at"] is not None
    assert parsed_result["global_id"] is not None

    # Intentionally masked RecordModel fields
    assert "pk" not in parsed_result
    assert "field_values" not in parsed_result
    assert "changes" not in parsed_result


class Presenter(BasePresenter[PersonModel]):
    fake_age = 26


class PydanticModel(BaseModel):
    name: str
    age: int


class PydanticPresenter(BasePresenter[PydanticModel]):
    fake_age = 26


@pytest.mark.asyncio
async def test_presenter_dumping(setup_in_memory_db):  # noqa: F811
    await setup_in_memory_db(["tests.unit.helpers.test_json"])

    model = PersonModel(name="John", age=30)
    await model.save()

    presenter = Presenter(model=model)
    assert presenter.fake_age == 26
    result = to_json(presenter)
    parsed_result = json.loads(result)
    assert parsed_result["name"] == "John"
    assert parsed_result["age"] == 30
    assert parsed_result["fake_age"] == 26

    pydantic_model = PydanticModel(name="John", age=30)
    pydantic_presenter = PydanticPresenter(model=pydantic_model)
    assert pydantic_presenter.fake_age == 26
    result = to_json(pydantic_presenter)
    parsed_result = json.loads(result)
    assert parsed_result["name"] == "John"
    assert parsed_result["age"] == 30
    assert parsed_result["fake_age"] == 26


def test_html_escaping_for_xss_protection():
    data = {
        "script": "<script>alert('xss')</script>",
        "img": '<img src=x onerror="alert(1)">',
        "url": "javascript:alert('xss')",
        "angle_brackets": "Label with < and > brackets",
        "ampersand": "Q&A section",
    }
    result = to_json(data)
    parsed = json.loads(result)

    assert parsed["script"] == "<script>alert('xss')</script>"
    assert parsed["img"] == '<img src=x onerror="alert(1)">'
    assert parsed["url"] == "javascript:alert('xss')"

    assert "\\u003c" in result
    assert "\\u003e" in result
    assert "\\u0026" in result
    assert "<script>" not in result
    assert "<img" not in result
    assert "Q&A" not in result
