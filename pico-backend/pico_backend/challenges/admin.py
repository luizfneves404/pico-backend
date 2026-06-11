from django import forms
from django.contrib import admin
from import_export.admin import ImportExportMixin

from .models import (
    Prize,
    Tournament,
    TournamentParticipation,
)


class BulkAddParticipantsForm(forms.Form):
    user_ids = forms.CharField(
        widget=forms.Textarea, help_text="Enter user IDs, one per line"
    )


@admin.register(Tournament)
class TournamentAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ("id", "name", "description", "start_time", "end_time")
    search_fields = ["name", "description"]


@admin.register(TournamentParticipation)
class TournamentParticipationAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "tournament__id",
        "tournament__name",
        "user__username",
        "created_at",
    )
    search_fields = ["tournament__id", "tournament__name", "user__username"]
    raw_id_fields = ("user", "tournament")


@admin.register(Prize)
class PrizeAdmin(admin.ModelAdmin):
    list_display = ("id", "tournament__name", "rank", "amount")
    search_fields = ["tournament__name"]
    raw_id_fields = ("tournament",)
