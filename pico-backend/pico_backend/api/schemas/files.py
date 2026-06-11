from ninja import Schema


class FileOut(Schema):
    id: int
    filename: str
    file_processing_done: bool | None


class FileGroupOut(Schema):
    id: int
    name: str
