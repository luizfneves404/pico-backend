from api.models import School
from django.db import connection


class SchoolNotFoundError(Exception):
    pass


async def list_schools():
    return [school async for school in School.objects.all()]


async def create_school(name: str):
    return await School.objects.acreate(name=name)


async def get_school(school_id: int):
    try:
        return await School.objects.aget(id=school_id)
    except School.DoesNotExist:
        raise SchoolNotFoundError


def get_school_ranking():
    sql = """
        WITH school_scores AS (
            SELECT 
                s.id,
                s.name,
                COALESCE(SUM(ui.dynamic_score), 0) as score
            FROM api_school s
            LEFT JOIN api_user u ON s.id = u.school_id
            LEFT JOIN quiz_userinfo ui ON u.id = ui.user_id
            GROUP BY s.id, s.name
        )
        SELECT 
            id,
            name,
            score,
            RANK() OVER (ORDER BY score DESC, id ASC) as rank
        FROM school_scores
        ORDER BY score DESC, id ASC;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
