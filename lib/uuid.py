from uuid import UUID


def parse_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def filter_valid_uuids(ids: list[str] | None) -> list[str] | None:
    if not ids:
        return None
    valid = [id_str for id_str in ids if id_str and parse_uuid(id_str)]
    return valid or None
