from badges.models import Badge


async def list_badges(user_id: int) -> list[Badge]:
    badges = [
        badge async for badge in Badge.objects.filter(users_earned__id=user_id).all()
    ]
    return badges
