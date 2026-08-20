from enum import StrEnum


class NotionNodeKind(StrEnum):
    PAGE = "page"
    DATABASE = "database"

    @property
    def is_page(self):
        return self == NotionNodeKind.PAGE

    @property
    def is_database(self):
        return self == NotionNodeKind.DATABASE
