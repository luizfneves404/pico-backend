from django.contrib import admin
from study_plans.models import StudyPlan

# Register your models here.


@admin.register(StudyPlan)
class StudyPlanAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "created_at")
    raw_id_fields = ["user"]
