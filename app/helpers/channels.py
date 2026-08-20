from infra.messaging import Topic


def topic_id(stream: str, **params) -> str:
    return Topic(stream, **params).name
