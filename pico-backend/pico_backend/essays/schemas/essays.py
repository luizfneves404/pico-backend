from ninja import Schema
from pydantic import AliasChoices, Field, model_validator


class FeedbackOut(Schema):
    id: int
    text: str
    grade: float
    feedback_category: str = Field(
        max_length=255,
        validation_alias=AliasChoices("feedback_category.name", "feedback_category"),
    )


class EssayOut(Schema):
    essay_type: str = Field(
        max_length=255,
        validation_alias=AliasChoices("essay_type.name", "essay_type"),
    )
    cleaned_text: str
    user_corrected_text: str
    feedback1: str = ""
    feedback2: str = ""
    feedback3: str = ""
    feedback4: str = ""
    feedback5: str = ""
    grade1: float | None = None
    grade2: float | None = None
    grade3: float | None = None
    grade4: float | None = None
    grade5: float | None = None
    feedbacks: list[FeedbackOut] = []

    # create feedback1, feedback2, feedback3, feedback4, feedback5 from feedbacks
    @model_validator(mode="after")
    def set_feedbacks(self):
        if len(self.feedbacks) == 5:
            self.feedback1 = self.feedbacks[0].text
            self.feedback2 = self.feedbacks[1].text
            self.feedback3 = self.feedbacks[2].text
            self.feedback4 = self.feedbacks[3].text
            self.feedback5 = self.feedbacks[4].text
            self.grade1 = self.feedbacks[0].grade
            self.grade2 = self.feedbacks[1].grade
            self.grade3 = self.feedbacks[2].grade
            self.grade4 = self.feedbacks[3].grade
            self.grade5 = self.feedbacks[4].grade
        return self


class EssayTopicIn(Schema):
    chatroom_id: int | None = None
    name: str = Field(max_length=255)


class EssayTopicOut(Schema):
    id: int
    name: str
    essay: EssayOut | None = None


class EssayCorrectionIn(Schema):
    user_corrected_text: str = Field(max_length=10000)
    essay_type: str = Field(
        max_length=255,
        default="Enem",
        validation_alias=AliasChoices("essay_type.name", "essay_type"),
    )
