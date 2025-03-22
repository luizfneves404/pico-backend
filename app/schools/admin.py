from schools.models import School
from sqladmin import ModelView


class SchoolAdmin(ModelView, model=School):
    column_list = [School.id, School.name]
    column_searchable_list = [School.id, School.name]
    column_sortable_list = [School.id, School.name]
    column_details_list = [School.id, School.name]
