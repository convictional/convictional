from uuid import UUID

from lib.uuid import filter_valid_uuids, parse_uuid

VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"


def test_parse_uuid():
    assert parse_uuid(VALID_UUID) == UUID(VALID_UUID)
    assert parse_uuid("not-a-uuid") is None
    assert parse_uuid("") is None
    assert parse_uuid(None) is None


def test_filter_valid_uuids():
    other = "660e8400-e29b-41d4-a716-446655440000"
    assert filter_valid_uuids([VALID_UUID, "bad", "", other]) == [VALID_UUID, other]
    assert filter_valid_uuids(["bad", ""]) is None
    assert filter_valid_uuids([]) is None
    assert filter_valid_uuids(None) is None
