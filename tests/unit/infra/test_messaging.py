import hashlib

from infra.messaging import (
    POSTGRES_TOPIC_NAME_MAX_BYTES,
    Topic,
    create_postgres_topic_name,
)


def test_create_postgres_topic_name():
    assert create_postgres_topic_name("") == "_"
    assert create_postgres_topic_name("workspace") == "workspace"
    assert create_postgres_topic_name("work-space:organization_id:123") == "work_space_organization_id_123"
    assert create_postgres_topic_name("1workspace") == "_1workspace"
    assert create_postgres_topic_name("wörkspace") == "w_rkspace"
    assert create_postgres_topic_name("WorkSpace") == "workspace"

    # Check very long name
    long_name = "a" * 100
    topic_name = create_postgres_topic_name(long_name)
    assert len(topic_name.encode("utf-8")) <= POSTGRES_TOPIC_NAME_MAX_BYTES

    # Check deterministic behavior
    input_name = "test:workspace:123"
    result1 = create_postgres_topic_name(input_name)
    result2 = create_postgres_topic_name(input_name)
    assert result1 == result2

    # Create a name that's exactly 63 bytes when converted
    name = "a" * 63
    topic_name = create_postgres_topic_name(name)
    assert len(topic_name.encode("utf-8")) == 63
    assert topic_name == name.lower()

    # Create a name that's 64 bytes (1 over limit)
    name = "a" * 64
    topic_name = create_postgres_topic_name(name)
    assert len(topic_name.encode("utf-8")) <= 63
    # Should contain hash suffix
    expected_hash = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    assert topic_name.endswith("_" + expected_hash)


def test_topic_init():
    topic = Topic("workspace", organization_id="123", user_id="456")
    assert topic.stream == "workspace"
    assert topic.params == {"organization_id": "123", "user_id": "456"}


def test_topic_name():
    # Test without params
    topic = Topic("workspace")
    assert topic.name == "workspace"

    # Test with params
    topic = Topic("workspace", organization_id="123", user_id="456")
    assert topic.name == "workspace:organization_id:123:user_id:456"

    # Test params are sorted
    topic = Topic("workspace", user_id="456", organization_id="123")
    assert topic.name == "workspace:organization_id:123:user_id:456"


def test_topic_matches():
    topic1 = Topic("workspace", organization_id="123")
    topic2 = Topic("workspace", organization_id="123")
    topic3 = Topic("workspace", organization_id="456")
    topic4 = Topic("other", organization_id="123")

    assert topic1.matches(topic2)
    assert not topic1.matches(topic3)
    assert not topic1.matches(topic4)


def test_topic_equality():
    topic1 = Topic("workspace", organization_id="123")
    topic2 = Topic("workspace", organization_id="123")
    topic3 = Topic("workspace", organization_id="456")

    assert topic1 == topic2
    assert topic1 != topic3
    assert topic1 != "not a topic"


def test_topic_hash():
    topic1 = Topic("workspace", organization_id="123")
    topic2 = Topic("workspace", organization_id="123")
    topic3 = Topic("workspace", organization_id="456")

    # Equal objects should have equal hashes
    assert hash(topic1) == hash(topic2)
    # Different objects should have different hashes
    assert hash(topic1) != hash(topic3)


def test_topic_str_repr():
    topic = Topic("workspace", organization_id="123")
    assert str(topic) == "workspace:organization_id:123"
    assert repr(topic) == "Topic('workspace', {'organization_id': '123'})"
