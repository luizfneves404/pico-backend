from django.contrib import admin

from .models import BonusEvent

# Register your models here.


@admin.register(BonusEvent)
class BonusEventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "multiplier",
        "created_at",
    )
    search_fields = ("name",)
    list_filter = ("created_at",)
    raw_id_fields = ("challenges", "sessions")
