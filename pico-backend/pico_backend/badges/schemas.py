from ninja import Schema


class BadgeOut(Schema):
    id: int
    title: str
    description: str
    image: str
    prize: int
