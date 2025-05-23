from app.education.models import College, Course, School
from app.shared.admin import Admin


class SchoolAdmin(Admin, model=School):
    column_list = [School.id, School.name]
    column_searchable_list = [School.id, School.name]
    column_sortable_list = [School.id, School.name]
    column_details_list = [School.id, School.name]


class CollegeAdmin(Admin, model=College):
    icon = "fa-solid fa-university"

    column_list = [College.id, College.name, College.user_submitted]
    column_searchable_list = [College.name]
    column_sortable_list = [College.id, College.name, College.user_submitted]

    form_columns = ["name", "user_submitted", "courses"]


class CourseAdmin(Admin, model=Course):
    icon = "fa-solid fa-book"

    column_list = [Course.id, Course.name, Course.user_submitted]
    column_searchable_list = [Course.name]
    column_sortable_list = [Course.id, Course.name, Course.user_submitted]

    form_columns = ["name", "user_submitted", "colleges"]
