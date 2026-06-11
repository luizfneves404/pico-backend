from django.contrib import admin
from currency.models import Currency, Transaction


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "value",
        "currency_type",
        "action",
        "is_default",
        "description",
        "created_at",
    )
    list_filter = ("currency_type", "action", "is_default")
    search_fields = ("description",)
    ordering = ("-created_at",)

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "value",
                    "currency_type",
                    "action",
                    "is_default",
                    "description",
                )
            },
        ),
        (
            "Related Object",
            {
                "fields": ("content_type", "object_id"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "currency",
        "amount",
        "description",
        "timestamp",
        "get_related_object",
    )
    list_filter = ("currency__currency_type", "currency__action", "timestamp")
    search_fields = ("user__username", "user__email", "description")
    raw_id_fields = ("user", "currency")
    readonly_fields = ("timestamp",)
    ordering = ("-timestamp",)

    def get_related_object(self, obj):
        if obj.related_object:
            return f"{obj.related_object._meta.model_name} ({obj.object_id})"
        return "-"

    get_related_object.short_description = "Related Object"

    fieldsets = (
        (
            None,
            {
                "fields": (("user", "currency"), "amount", "description", "timestamp"),
            },
        ),
        (
            "Related Object",
            {
                "fields": ("content_type", "object_id"),
                "classes": ("collapse",),
            },
        ),
    )
