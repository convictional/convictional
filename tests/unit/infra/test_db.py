import base64
from datetime import date, datetime
from typing import Any
from uuid import UUID
from uuid import uuid4 as generate_uuid

import pytest
from pydantic import BaseModel
from tortoise import fields

from infra.db import (
    GlobalID,
    InvalidGlobalIDParamError,
    Pagination,
    PydanticField,
    PydanticListField,
    RecordModel,
    _diff_fields,
)
from lib.json import Decoder, Encoder
from tests.helpers.db import setup_in_memory_db  # noqa: F401


def test_changes():
    class TestModel(RecordModel):
        name = fields.CharField(max_length=255, null=True)
        age = fields.IntField(null=True)

    model = TestModel(name="John", age=30)
    assert model.changes == {"name": (None, "John"), "age": (None, 30)}

    model._original_change_tracking_field_values = {"name": "John", "age": 30}
    assert model.changes == {}

    model.name = "Jane"
    model.age = 31
    assert model.changes == {"name": ("John", "Jane"), "age": (30, 31)}


def test_diff_fields():
    # No differences
    original: dict[str, Any] = {"a": 1, "b": 2}
    new = {"a": 1, "b": 2}
    assert _diff_fields(original, new) == {}

    # Differences
    original = {"a": 1, "b": 2}
    new = {"a": 2, "b": 2}
    assert _diff_fields(original, new) == {"a": (1, 2)}

    # New keys
    original = {"a": 1}
    new = {"a": 1, "b": 2}
    assert _diff_fields(original, new) == {"b": (None, 2)}

    # Missing keys
    original = {"a": 1, "b": 2}
    new = {"a": 1}
    assert _diff_fields(original, new) == {"b": (2, None)}

    # None values
    original = {"a": 1, "b": None}
    new = {"a": 1, "b": 2}
    assert _diff_fields(original, new) == {"b": (None, 2)}


def test_field_values():
    class TestModel(RecordModel):
        name = fields.CharField(max_length=255, null=True)
        age = fields.IntField(null=True)

    model = TestModel(name="John", age=30)
    assert "id" in model.field_values
    assert model.field_values["name"] == "John"
    assert model.field_values["age"] == 30

    model.name = "Jane"
    model.age = 31
    assert "id" in model.field_values
    assert model.field_values["name"] == "Jane"
    assert model.field_values["age"] == 31


def test_json_field():
    uuid_obj = UUID("12345678123456781234567812345678")
    datetime_obj = datetime(2020, 1, 1, 12, 0)
    date_obj = date(2022, 1, 17)
    set_obj = {1, 2, 3}

    encoder = Encoder()
    encoded = encoder.encode(uuid_obj)
    assert encoded == '{"__uuid__": true, "value": "12345678-1234-5678-1234-567812345678"}'
    encoded = encoder.encode(datetime_obj)
    assert encoded == '{"__datetime__": true, "value": "2020-01-01T12:00:00"}'
    encoded = encoder.encode(date_obj)
    assert encoded == '{"__date__": true, "value": "2022-01-17"}'

    decoder = Decoder()
    encoded = '{"__uuid__": true, "value": "12345678-1234-5678-1234-567812345678"}'
    decoded = decoder.decode(encoded)
    assert decoded == uuid_obj

    encoded = '{"__datetime__": true, "value": "2020-01-01T12:00:00"}'
    decoded = decoder.decode(encoded)
    assert decoded == datetime_obj

    encoded = '{"__date__": true, "value": "2022-01-17"}'
    decoded = decoder.decode(encoded)
    assert decoded == date_obj

    encoded_uuid = encoder.encode(uuid_obj)
    encoded_datetime = encoder.encode(datetime_obj)
    encoded_date = encoder.encode(date_obj)
    encoded_set = encoder.encode(set_obj)
    decoded_uuid = decoder.decode(encoded_uuid)
    decoded_datetime = decoder.decode(encoded_datetime)
    decoded_date = decoder.decode(encoded_date)
    decoded_set = decoder.decode(encoded_set)
    assert decoded_uuid == uuid_obj
    assert decoded_datetime == datetime_obj
    assert decoded_date == date_obj
    assert decoded_set == set_obj


class PydanticModel(BaseModel):
    user_id: UUID | None = None
    invited_at: datetime | None = None
    status: str | None = None


class DBModelWithPydanticField(RecordModel):
    something_else = fields.CharField(max_length=255, null=True)
    invite: PydanticModel = PydanticField(pydantic_model=PydanticModel)  # type: ignore


class DBModelWithPydanticList(RecordModel):
    something_else = fields.CharField(max_length=255, null=True)
    invites: list[PydanticModel] = PydanticListField(pydantic_model=PydanticModel, default=[])  # type: ignore


@pytest.mark.asyncio
async def test_pydantic_field(setup_in_memory_db):  # noqa: F811
    await setup_in_memory_db(["tests.unit.infra.test_db"])
    invite = PydanticModel(
        user_id=UUID("12345678123456781234567812345678"),
        invited_at=datetime(2020, 1, 1, 12, 0),
        status="active",
    )

    # Save the model
    model = DBModelWithPydanticField(
        invite=invite,
    )
    await model.save()

    # Retrieve the model
    retrieved_model = await DBModelWithPydanticField.get(id=model.id)
    assert retrieved_model.invite == invite

    # Modify and update
    retrieved_model.invite.status = "inactive"
    await retrieved_model.save()

    # Retrieve the model
    retrieved_model = await DBModelWithPydanticField.get(id=model.id)
    assert retrieved_model.invite.status == "inactive"


@pytest.mark.asyncio
async def test_pydantic_listfield(setup_in_memory_db):  # noqa: F811
    await setup_in_memory_db(["tests.unit.infra.test_db"])
    invite = PydanticModel(
        user_id=UUID("12345678123456781234567812345678"),
        invited_at=datetime(2020, 1, 1, 12, 0),
        status="active",
    )

    # Save the model
    model = DBModelWithPydanticList(
        invites=[invite],
    )
    await model.save()

    # Retrieve the model
    retrieved_model = await DBModelWithPydanticList.get(id=model.id)
    assert retrieved_model.invites == [invite]

    # Add another invite
    invite_2 = PydanticModel(
        user_id=UUID("22345678123456781234567812345678"),
        invited_at=datetime(2020, 1, 1, 12, 0),
        status="active",
    )
    retrieved_model.invites.append(invite_2)
    await retrieved_model.save()

    # Retrieve the model
    retrieved_model = await DBModelWithPydanticList.get(id=model.id)
    assert retrieved_model.invites == [invite, invite_2]

    # Test deserialization
    assert isinstance(retrieved_model.invites[0], PydanticModel)
    assert retrieved_model.invites[0].user_id == UUID("12345678123456781234567812345678")
    assert retrieved_model.invites[0].status == "active"
    assert retrieved_model.invites[0].invited_at == datetime(2020, 1, 1, 12, 0)


def test_global_id_equality():
    gid_1_id = generate_uuid()
    gid_2_id = generate_uuid()
    gid = GlobalID.parse(f"gid://convictional/Goal/{gid_1_id}")
    gid_2 = GlobalID.parse(f"gid://convictional/Goal/{gid_2_id}")

    assert gid == f"gid://convictional/Goal/{gid_1_id}"
    assert gid != gid_2
    assert gid != f"http://convictional/Goal/{gid_1_id}"


def test_global_id_param():
    string = "gid://convictional/Goal/550e8400-e29b-41d4-a716-446655440000"
    param = GlobalID.parse(string).to_param
    from_param = GlobalID.from_param(param)
    assert isinstance(from_param, GlobalID)
    assert from_param == GlobalID.parse(string)

    with pytest.raises(InvalidGlobalIDParamError) as exc_info:
        GlobalID.from_param("invalid base64")
    assert "Invalid base64 encoding" in str(exc_info.value)

    invalid_unicode = base64.b64encode(b"\xff\xfe").decode()
    with pytest.raises(InvalidGlobalIDParamError) as exc_info:
        GlobalID.from_param(invalid_unicode)
    assert "Unable to decode parameter" in str(exc_info.value)


def test_pagination_cursor_encoding():
    # Test valid cursor encoding
    cursor_data = [("field1", "value1"), ("field2", 2)]
    valid_cursor = Pagination.encode_cursor(cursor_data)
    decoded = Pagination.decode_cursor(valid_cursor)
    assert decoded == cursor_data

    # Test with missing padding
    valid_no_padding = valid_cursor[:-2]
    decoded = Pagination.decode_cursor(valid_no_padding)
    assert decoded == cursor_data

    # Test with invalid base64
    invalid_cursor = "invalid!base64"
    decoded = Pagination.decode_cursor(invalid_cursor)
    assert decoded == []

    # Test with valid base64 but invalid JSON
    invalid_json = base64.b64encode(b"not valid json").decode()
    decoded = Pagination.decode_cursor(invalid_json)
    assert decoded == []
