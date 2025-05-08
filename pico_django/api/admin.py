import csv
import io
from typing import Any

import api.services.chatroom_service as chatroom_service
import api.services.file_service as file_service
import api.services.message_service as message_service
import api.services.user_service as user_service
import pico_backend.amp as pico_backend_amp
import quiz.quiz_service as quiz_service
from api import fcm_tasks
from api.forms import (
    BulkEmailForm,
    BulkMessageForm,
    EmbeddingCSVUploadForm,
    NotificationForm,
    VariableBulkMessageForm,
)
from api.models import (
    SENTINEL_USERNAMES,
    Chatroom,
    College,
    Course,
    EmbeddedFile,
    EmbeddedTextChunk,
    FileGroup,
    Membership,
    Message,
    OfficialChatroom,
    School,
    User,
)
from asgiref.sync import async_to_sync
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.db.models import Count, Prefetch, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html

# from fcm_django.admin import DeviceAdmin
# from fcm_django.models import FCMDevice
from import_export import resources
from import_export.admin import ImportExportMixin


class EmbeddedFileMessagesInline(admin.TabularInline):
    model = EmbeddedFile.messages.through
    extra = 1


class CourseInline(admin.TabularInline):
    model = College.courses.through
    extra = 1
    raw_id_fields = ["course"]


@admin.register(College)
class CollegeAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "user_submitted"]
    list_filter = ["user_submitted"]
    search_fields = ["id", "name"]
    raw_id_fields = ["courses"]
    inlines = [CourseInline]
    exclude = ["courses"]  # Exclude courses field since we're using inline

    def get_queryset(self, request):
        queryset = super().get_queryset(request).prefetch_related("courses")
        return queryset


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "user_submitted"]
    list_filter = ["user_submitted"]
    search_fields = ["id", "name"]


class SchoolResource(resources.ModelResource):
    class Meta:
        model = School
        use_bulk = True
        fields = ["id", "name", "user_submitted", "inep_code"]


@admin.register(School)
class SchoolAdmin(ImportExportMixin, admin.ModelAdmin):
    resource_class = SchoolResource
    list_display = ["id", "name", "user_submitted", "inep_code"]
    list_filter = ["user_submitted"]
    search_fields = ["id", "name", "inep_code"]


class UserResource(resources.ModelResource):
    total_answers = resources.Field(readonly=True)
    date_joined = resources.Field(readonly=True)
    referral_count = resources.Field(readonly=True)

    class Meta:
        use_bulk = True
        model = User
        import_id_fields = ("id",)
        fields = [
            "id",
            "username",
            "password",
            "phone_number",
            "email",
            "is_premium",
            "school",
            "chosen_college",
            "chosen_course",
            "education_level",
            "signup_source",
            "referred_by__username",
            "referral_count",
            "commitment",
            "is_staff",
            "is_superuser",
            "total_answers",
            "date_joined",
            "balance",
        ]

    def filter_export(self, queryset: QuerySet[User], **kwargs: Any) -> QuerySet:
        return (
            queryset.exclude(username__in=SENTINEL_USERNAMES)
            .with_referral_count()
            .annotate(
                total_answers=Count("session_question_user_set", distinct=True),
            )
        )

    def before_save_instance(
        self, instance: User, row: dict[str, Any], **kwargs: Any
    ) -> None:
        instance.set_password(row["password"])

    def dehydrate_total_answers(self, user: User) -> int:
        return getattr(user, "total_answers", 0)

    def dehydrate_date_joined(self, user: User) -> str:
        return user.date_joined.strftime("%Y-%m-%d %H:%M:%S")

    def dehydrate_referral_count(self, user: User) -> int:
        return getattr(user, "referral_count", 0)


@admin.register(User)
class CustomUserAdmin(ImportExportMixin, UserAdmin):
    resource_class = UserResource
    model = User
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "username",
                    "password",
                    "phone_number",
                    "email",
                    "date_joined",
                    "is_premium",
                    "school",
                    "chosen_college",
                    "chosen_course",
                    "education_level",
                    "signup_source",
                    "referred_by",
                    "referral_count",
                    "commitment",
                    "balance",
                    "is_bot",
                    "bot_difficulty",
                )
            },
        ),
        ("Permissions", {"fields": ("is_staff", "is_superuser")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "phone_number",
                    "email",
                    "password1",
                    "password2",
                    "is_premium",
                    "school",
                    "chosen_college",
                    "chosen_course",
                    "education_level",
                    "signup_source",
                    "referred_by",
                    "commitment",
                    "balance",
                    "is_staff",
                    "is_superuser",
                    "is_bot",
                    "bot_difficulty",
                ),
            },
        ),
    )
    list_display = [
        "id",
        "username",
        "phone_number",
        "email",
        "date_joined",
        "is_premium",
        "school",
        "chosen_college",
        "chosen_course",
        "education_level",
        "signup_source",
        "referred_by__username",
        "commitment",
        "referral_count",
        "balance",
        "is_staff",
        "is_superuser",
        "is_bot",
        "bot_difficulty",
    ]
    readonly_fields = ["referral_count"]
    ordering = ["id"]
    search_fields = ["id", "username", "phone_number", "email"]
    list_filter = [
        "is_staff",
        "is_superuser",
        "is_premium",
        "school",
        "education_level",
        "signup_source",
        "is_bot",
    ]
    actions = [
        "create_official_chatroom_if_not_exists",
        "export_user_stats",
        "send_bulk_email_action",
        "send_bulk_custom_quiz_messages_action",
        "send_bulk_stats_messages_action",
        "send_bulk_notification",
    ]
    raw_id_fields = ["referred_by"]

    def referral_count(self, obj: User) -> int:
        return obj.referral_count

    referral_count.short_description = "Referral Count"
    referral_count.admin_order_field = "referral_count"

    def delete_model(self, request: HttpRequest, obj: User) -> None:
        pico_backend_amp.delete_user(obj.id)
        super().delete_model(request, obj)

    def get_urls(self) -> list:
        urls = super().get_urls()
        custom_urls = [
            path(
                "send-bulk-email/",
                self.admin_site.admin_view(self.send_bulk_email_view),
                name="send_bulk_email_view",
            ),
            path(
                "send-bulk-notification/",
                self.admin_site.admin_view(self.send_bulk_notification_view),
                name="send_bulk_notification_view",
            ),
        ]
        return custom_urls + urls

    def get_queryset(self, request: HttpRequest) -> QuerySet[User]:
        return (
            super()
            .get_queryset(request)
            .select_related("school", "chosen_college", "chosen_course")
            .with_referral_count()
        )

    def send_bulk_email_view(self, request: HttpRequest) -> HttpResponse:
        if request.method == "POST":
            form = BulkEmailForm(request.POST, request.FILES)
            if form.is_valid():
                user_ids = request.session.get("selected_users_for_bulk_email", [])
                users = [user for user in User.objects.filter(id__in=user_ids)]

                subject = form.cleaned_data["subject"]
                template = request.FILES["html_file"].read().decode("utf-8")

                user_service.send_bulk_email(users, subject, template, 5)

                del request.session["selected_users_for_bulk_email"]
                messages.success(request, "Emails have been sent successfully.")
                return HttpResponseRedirect("../")
        else:
            form = BulkEmailForm()
            selected_users = request.session.get("selected_users_for_bulk_email", [])
            if not selected_users:
                messages.error(request, "No users selected for emailing.")
                return HttpResponseRedirect("../")

        return render(request, "admin/bulk_email_form.html", {"form": form})

    @admin.action(description="Send a bulk one-off email to selected users")
    def send_bulk_email_action(
        self, request: HttpRequest, queryset: QuerySet[User]
    ) -> HttpResponseRedirect:
        request.session["selected_users_for_bulk_email"] = [
            user.id for user in queryset
        ]
        url = reverse("admin:send_bulk_email_view")
        return HttpResponseRedirect(url)

    @admin.action(
        description="Create official chatroom with predefined messages for selected users"
    )
    def create_official_chatroom_if_not_exists(
        self, request: HttpRequest, queryset: QuerySet[User]
    ) -> None:
        existing_chatroom_user_ids = set(
            OfficialChatroom.objects.filter(members__in=queryset).values_list(
                "members__id", flat=True
            )
        )

        new_chatrooms_count = 0

        for user in queryset:
            if user.id not in existing_chatroom_user_ids:
                async_to_sync(
                    chatroom_service.create_predefined_chatroom_with_messages
                )(
                    user_service.YOU_AND_PICO_CHATROOM_NAME,
                    user,
                    [],
                    user_service.YOU_AND_PICO_CHATROOM_MESSAGES,
                )
                new_chatrooms_count += 1

        self.message_user(
            request, f"Created {new_chatrooms_count} new official chatrooms."
        )

    @admin.action(
        description="Export user info (username, date joined, number of answers, areas stats)"
    )
    def export_user_stats(
        self, request: HttpRequest, queryset: QuerySet[User]
    ) -> HttpResponse:
        response = HttpResponse(
            content_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="user_infos.csv"'},
        )
        writer = csv.writer(response)
        # Define column headers
        headers = [
            "username",
            "Date Joined",
            "Total Answers",
            "Worst Area",
            "Matematica Total Answers",
            "Matematica Correct Answers",
            "Matematica proportion correct",
            "Natureza Total Answers",
            "Natureza Correct Answers",
            "Natureza proportion correct",
            "Humanas Total Answers",
            "Humanas Correct Answers",
            "Humanas proportion correct",
            "Linguagens Total Answers",
            "Linguagens Correct Answers",
            "Linguagens proportion correct",
        ]

        # Write column headers to the CSV
        writer.writerow(headers)

        # Filter out sentinel usernames
        filtered_users = [
            user for user in queryset if user.username not in SENTINEL_USERNAMES
        ]

        # Retrieve user information and statistics
        user_infos: list[UserInfo] = user_service.get_user_infos(filtered_users)
        user_stats: dict[str, UserStats] = quiz_service.get_user_statistics(
            filtered_users
        )

        def get_stat(stat_dict: dict[str, Any], area: str, stat_type: str) -> int:
            return stat_dict["areas"].get(area, {}).get(stat_type, 0)

        # Write user data to the CSV
        for info in user_infos:
            username = info["username"]
            user_stat = user_stats[username]

            row = [
                username,
                info["date_joined"],
                info["total_answers"],
                user_stat["worst_area"],
                get_stat(user_stat, "Matemática", "total_answers"),
                get_stat(user_stat, "Matemática", "correct_answers"),
                get_stat(user_stat, "Matemática", "proportion_correct"),
                get_stat(user_stat, "Ciências da Natureza", "total_answers"),
                get_stat(user_stat, "Ciências da Natureza", "correct_answers"),
                get_stat(user_stat, "Ciências da Natureza", "proportion_correct"),
                get_stat(user_stat, "Ciências Humanas", "total_answers"),
                get_stat(user_stat, "Ciências Humanas", "correct_answers"),
                get_stat(user_stat, "Ciências Humanas", "proportion_correct"),
                get_stat(user_stat, "Linguagens", "total_answers"),
                get_stat(user_stat, "Linguagens", "correct_answers"),
                get_stat(user_stat, "Linguagens", "proportion_correct"),
            ]

            writer.writerow(row)

        return response

    @admin.action(description="Send bulk notification to selected users")
    def send_bulk_notification(
        self, request: HttpRequest, queryset: QuerySet[User]
    ) -> HttpResponseRedirect:
        """
        Admin action to send bulk notifications to selected users.
        """
        # Always set the selected users, regardless of whether the key exists
        request.session["selected_users_for_notification"] = [
            user.id for user in queryset
        ]
        url = reverse("admin:send_bulk_notification_view")
        return HttpResponseRedirect(url)

    def send_bulk_notification_view(self, request: HttpRequest) -> HttpResponse:
        if request.method == "POST":
            form = NotificationForm(request.POST)
            if form.is_valid():
                user_ids = request.session.get("selected_users_for_notification", [])
                title = form.cleaned_data["title"]
                body = form.cleaned_data["body"]

                try:
                    fcm_tasks.task_send_notification.delay(user_ids, title, body)
                    messages.success(
                        request,
                        f"Successfully sent notification to {len(user_ids)} users.",
                    )
                except Exception as e:
                    messages.error(request, f"Error sending notifications: {str(e)}")

                del request.session["selected_users_for_notification"]
                return HttpResponseRedirect("../")
        else:
            form = NotificationForm()
            selected_users = request.session.get("selected_users_for_notification", [])
            if not selected_users:
                messages.error(request, "No users selected for notification.")
                return HttpResponseRedirect("../")

        return render(
            request,
            "admin/send_notification_confirmation.html",
            {
                "form": form,
                "title": "Send Notification",
                "users_count": len(
                    request.session.get("selected_users_for_notification", [])
                ),
            },
        )


@admin.register(Chatroom)
class ChatroomAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "name",
        "timestamp",
        "chat_type",
        "members_list",
        "view_messages_link",
    ]
    search_fields = ["id", "name"]
    list_filter = ["timestamp", "chat_type"]
    actions = ["bulk_message_action", "variable_bulk_message_action"]

    def view_messages_link(self, obj):
        url = reverse("admin:api_message_changelist") + f"?chatroom__id__exact={obj.id}"
        return format_html('<a href="{}">View Messages</a>', url)

    view_messages_link.short_description = "Messages"  # Optional: Set column header

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "send_bulk_message/",
                self.admin_site.admin_view(self.send_bulk_message_view),
                name="api_chatroom_send_bulk_message",
            ),
            path(
                "send_variable_bulk_message/",
                self.admin_site.admin_view(self.send_variable_bulk_message_view),
                name="api_chatroom_send_variable_bulk_message",
            ),
        ]
        return custom_urls + urls

    def send_bulk_message_view(self, request):
        if request.method == "POST":
            form = BulkMessageForm(request.POST, request.FILES)
            if form.is_valid():
                chatrooms = Chatroom.objects.filter(
                    id__in=request.session.get("chatrooms_for_bulk_message", [])
                )
                message_context = [
                    message_service.MessageContext(
                        sender="pico",
                        content=form.cleaned_data["content"],
                        chatroom=chatroom,
                        attachment=form.cleaned_data.get("attachment"),
                        essay_topic=form.cleaned_data.get("essay_topic_id"),
                        session=form.cleaned_data.get("session_id"),
                    )
                    for chatroom in chatrooms
                ]
                message_service.send(message_context=message_context)
                del request.session["chatrooms_for_bulk_message"]
                messages.success(request, "Messages sent successfully.")
                return HttpResponseRedirect("../")
        else:
            form = BulkMessageForm()
            # Assuming the user had previously selected chatrooms for messaging
            selected_chatrooms = request.session.get("chatrooms_for_bulk_message", [])
            if not selected_chatrooms:
                messages.error(request, "No chatrooms selected for messaging.")
                return HttpResponseRedirect("../")

        return render(request, "admin/send_bulk_message.html", {"form": form})

    def bulk_message_action(self, request, queryset):
        request.session["chatrooms_for_bulk_message"] = [
            chatroom.id for chatroom in queryset
        ]
        url = reverse("admin:api_chatroom_send_bulk_message")
        return HttpResponseRedirect(url)

    bulk_message_action.short_description = "Send bulk message to selected chatrooms"

    def send_variable_bulk_message_view(self, request):
        if request.method == "POST":
            form = VariableBulkMessageForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES["csv_file"]
                decoded_file = csv_file.read().decode("utf-8")
                io_string = io.StringIO(decoded_file)
                reader = csv.DictReader(io_string)

                content_user_map = {}
                usernames = set()

                for row in reader:
                    username = row.get("username")
                    content = row.get("content")
                    if not username or not content:
                        messages.error(
                            request,
                            f"Invalid row: {row}. Both username and content are required.",
                        )
                        return HttpResponseRedirect("../")
                    content_user_map[username] = content
                    usernames.add(username)

                users = list(User.non_sentinel_objects.filter(username__in=usernames))

                if len(users) != len(usernames):
                    found_usernames = set(user.username for user in users)
                    missing_usernames = usernames - found_usernames
                    messages.error(
                        request,
                        f"Some usernames were not found: {', '.join(missing_usernames)}",
                    )
                    return HttpResponseRedirect("../")

                content_users_pairs = [
                    (content_user_map[user.username], user) for user in users
                ]

                try:
                    message_service.send_messages_to_user_official_chatrooms(
                        content_users_pairs,
                        attachment=form.cleaned_data.get("attachment"),
                        essay_topic=form.cleaned_data.get("essay_topic"),
                        session=form.cleaned_data.get("session"),
                    )
                except ValueError as e:
                    messages.error(request, f"Error sending messages: {e}")
                else:
                    messages.success(
                        request, f"Messages sent successfully to {len(users)} users."
                    )
                return HttpResponseRedirect("../")
        else:
            form = VariableBulkMessageForm()

        return render(request, "admin/send_variable_bulk_message.html", {"form": form})

    def variable_bulk_message_action(self, request, queryset):
        url = reverse("admin:api_chatroom_send_variable_bulk_message")
        return HttpResponseRedirect(url)

    def get_queryset(self, request):
        # Prefetching membership and related user data to minimize queries
        membership_prefetch = Prefetch(
            "membership_set", queryset=Membership.objects.select_related("user")
        )
        queryset = super().get_queryset(request).prefetch_related(membership_prefetch)
        return queryset

    def members_list(self, obj) -> str:
        # Accessing prefetched memberships and their user data efficiently
        member_usernames = [
            membership.user.username for membership in obj.membership_set.all()
        ]
        return ", ".join(member_usernames)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["id", "chatroom", "user", "role"]
    search_fields = ["chatroom__name", "user__username"]
    list_filter = ["role"]
    raw_id_fields = ["chatroom", "user"]
    ordering = ["id"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("chatroom", "user")
        return queryset


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "sender",
        "content",
        "timestamp",
        "chatroom",
        "essay_topic",
        "session",
    ]
    search_fields = [
        "id",
        "sender__username",
        "content",
        "chatroom__name",
        "chatroom__members__username",
    ]
    list_filter = ["timestamp"]
    fields = [
        "sender",
        "content",
        "chatroom",
        "parent_message",
        "embedding",
        "essay_topic",
        "session",
    ]
    raw_id_fields = ["parent_message", "chatroom", "sender", "essay_topic", "session"]
    inlines = [EmbeddedFileMessagesInline]
    ordering = ["-timestamp"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            message_service.process_created_messages(
                [obj],
                [
                    message_service.MessageContext(
                        sender=obj.sender,
                        content=obj.content,
                        chatroom=obj.chatroom,
                        parent_message=obj.parent_message,
                        essay_topic=obj.essay_topic,
                        session=obj.session,
                    )
                ],
            )


@admin.register(EmbeddedFile)
class EmbeddedFileAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "file_group"]
    search_fields = ["id", "name"]
    raw_id_fields = ["file_group", "messages"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            file_service.handle_global_file(obj.id, obj.file)


@admin.register(EmbeddedTextChunk)
class EmbeddedTextChunkAdmin(admin.ModelAdmin):
    change_list_template = "admin/custom_embedded_text_chunk_change_list.html"
    list_display = ["id", "embedded_file_id", "text"]
    search_fields = ["id", "embedded_file__name", "embedded_file__id", "text"]
    ordering = ["embedded_file"]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "add-chunks-to-embed-csv/",
                self.add_chunks_to_embed_csv,
                name="add_chunks_to_embed_csv",
            ),
        ]
        return custom_urls + urls

    def embedded_file_id(self, obj) -> int:
        return obj.embedded_file.id

    def add_chunks_to_embed_csv(self, request):
        if request.method == "POST":
            form = EmbeddingCSVUploadForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES["csv_file"]
                decoded_file = csv_file.read().decode("utf-8")
                io_string = io.StringIO(decoded_file)
                reader = csv.DictReader(io_string)

                text_chunks = [row["chunk"] for row in reader]

                file_group = form.cleaned_data["file_group"]

                embedded_file = EmbeddedFile.objects.create(
                    name=csv_file.name,
                    file=csv_file,
                    file_group=file_group,
                )

                file_service.embed_and_add_text_chunks_to_file(
                    embedded_file.id, text_chunks
                )

                self.message_user(
                    request,
                    f"Text chunks will be embedded and added to embedded file {embedded_file.id}",
                )
                return HttpResponseRedirect("..")
        else:
            form = EmbeddingCSVUploadForm()

        context = {"form": form}
        return render(request, "admin/csv_form.html", context)


@admin.register(FileGroup)
class FileGroupAdmin(admin.ModelAdmin):
    list_display = ["id", "name"]
    search_fields = ["id", "name"]


""" # deregister fcm device admin
admin.site.unregister(FCMDevice) """


""" class FCMDeviceResource(resources.ModelResource):
    class Meta:
        model = FCMDevice
        use_bulk = True
        fields = ["id", "user", "registration_id", "type"] """


""" @admin.register(FCMDevice)
class FCMDeviceAdmin(ImportExportMixin, DeviceAdmin):
    resource_class = FCMDeviceResource """
