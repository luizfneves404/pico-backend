"""class FeedbackCategoryInline(admin.TabularInline):
    model = FeedbackCategory
    extra = 1


@admin.register(EssayType)
class EssayTypeAdmin(admin.ModelAdmin):
    ordering = ["name"]
    search_fields = ["name"]
    fields = ["name", "number_of_categories"]
    list_display = ["name", "number_of_categories"]
    inlines = [FeedbackCategoryInline]
    readonly_fields = ["number_of_categories"]

    def number_of_categories(self, obj):
        return obj.feedback_categories_count

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(feedback_categories_count=models.Count("feedback_categories"))
        )


class ExtractedTextInline(admin.TabularInline):
    model = ExtractedText
    extra = 1


class FeedbackInline(admin.TabularInline):
    model = Feedback
    extra = 1
    ordering = ["feedback_category__name"]


@admin.register(Essay)
class EssayAdmin(admin.ModelAdmin):
    ordering = ["id"]
    search_fields = [
        "id",
        "author__username",
        "user_corrected_text",
        "essay_topic__name",
        "essay_type__name",
    ]
    list_display = ["id", "created_at", "author", "essay_topic", "essay_type"]
    list_filter = ["essay_type"]
    actions = ["extract_text", "clean_text", "extract_and_clean_text", "correct_text"]
    inlines = [ExtractedTextInline, FeedbackInline]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("essay_type", "essay_topic", "author")
        )

    def extract_text(self, request, queryset):
        essay_service.extract_text_and_save(list(queryset.values_list("id", flat=True)))

    extract_text.short_description = (
        "Extract text from selected Essays and store it in the extracted_text fields"
    )

    def clean_text(self, request, queryset):
        essay_service.clean_text_and_save(list(queryset.values_list("id", flat=True)))

    clean_text.short_description = (
        "Clean text from selected Essays and store it in the cleaned_text field"
    )

    def extract_and_clean_text(self, request, queryset):
        essay_service.extract_and_clean_and_save_and_notify(
            list(queryset.values_list("id", flat=True))
        )

    extract_and_clean_text.short_description = "Extract text from selected Essays, clean it, and store it in the cleaned_text field"

    def correct_text(self, request, queryset):
        essay_service.correct_essay_and_save_and_notify(
            list(queryset.values_list("id", flat=True))
        )

    correct_text.short_description = "Correct text from selected Essays, using user_corrected_text, and store it in the feedback fields"


@admin.register(EssayTopic)
class EssayTopicAdmin(admin.ModelAdmin):
    ordering = ["id"]
    search_fields = ["id", "name"]
    fields = ["name"]
    list_display = ["id", "name"]
"""
