from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class EssayType(models.Model):
    name = models.CharField(max_length=255, primary_key=True)

    def __str__(self):
        return self.name


class FeedbackCategory(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    essay_type = models.ForeignKey(
        EssayType, on_delete=models.CASCADE, related_name="feedback_categories"
    )
    prompt_template = models.TextField()
    temperature = models.FloatField(default=0)

    def __str__(self):
        return self.name


class EssayTopic(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def content_str(self):
        return f"Essay topic: {self.name}"

    class Meta:
        verbose_name_plural = "essay topics"


class Essay(models.Model):
    id = models.BigAutoField(primary_key=True)
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="essays",
    )
    original_file = models.FileField(upload_to="essays/files/", blank=True)
    cleaned_text = models.TextField(blank=True, default="")
    user_corrected_text = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    essay_topic = models.ForeignKey(
        EssayTopic, on_delete=models.CASCADE, related_name="essays"
    )
    essay_type = models.ForeignKey(
        EssayType, on_delete=models.PROTECT, related_name="essays"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["author", "essay_topic"],
                name="unique_essay_per_user_per_topic",
            )
        ]


class ExtractedText(models.Model):
    id = models.BigAutoField(primary_key=True)
    essay = models.ForeignKey(
        Essay, on_delete=models.CASCADE, related_name="extracted_texts"
    )
    extraction_method = models.CharField(max_length=255)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class Feedback(models.Model):
    id = models.BigAutoField(primary_key=True)
    essay = models.ForeignKey(Essay, on_delete=models.CASCADE, related_name="feedbacks")
    text = models.TextField()
    grade = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    feedback_category = models.ForeignKey(
        FeedbackCategory, on_delete=models.PROTECT, related_name="feedbacks"
    )

    class Meta:
        ordering = ["feedback_category__name"]
