# Using pgvector 0.4.0
import datetime
import decimal
from typing import Any, List, Optional

from pgvector.sqlalchemy.vector import VECTOR
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Double,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ApiChatroom(Base):
    __tablename__ = "api_chatroom"
    __table_args__ = (PrimaryKeyConstraint("id", name="api_chatroom_pkey"),)

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    name: Mapped[str] = mapped_column(String(120))
    icon: Mapped[str] = mapped_column(String(100))
    chat_type: Mapped[str] = mapped_column(String(2))

    api_membership: Mapped[List["ApiMembership"]] = relationship(
        "ApiMembership", back_populates="chatroom"
    )
    api_message: Mapped[List["ApiMessage"]] = relationship(
        "ApiMessage", back_populates="chatroom"
    )


class ApiCollege(Base):
    __tablename__ = "api_college"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="api_college_pkey"),
        UniqueConstraint("name", name="unique_college_name"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(120))
    user_submitted: Mapped[bool] = mapped_column(Boolean)

    api_college_courses: Mapped[List["ApiCollegeCourses"]] = relationship(
        "ApiCollegeCourses", back_populates="college"
    )
    api_user: Mapped[List["ApiUser"]] = relationship(
        "ApiUser", back_populates="chosen_college"
    )


class ApiCourse(Base):
    __tablename__ = "api_course"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="api_course_pkey"),
        UniqueConstraint("name", name="unique_course_name"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(120))
    user_submitted: Mapped[bool] = mapped_column(Boolean)

    api_college_courses: Mapped[List["ApiCollegeCourses"]] = relationship(
        "ApiCollegeCourses", back_populates="course"
    )
    api_user: Mapped[List["ApiUser"]] = relationship(
        "ApiUser", back_populates="chosen_course"
    )


class ApiFilegroup(Base):
    __tablename__ = "api_filegroup"
    __table_args__ = (PrimaryKeyConstraint("id", name="api_filegroup_pkey"),)

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(120))

    api_embeddedfile: Mapped[List["ApiEmbeddedfile"]] = relationship(
        "ApiEmbeddedfile", back_populates="file_group"
    )


class ApiSchool(Base):
    __tablename__ = "api_school"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="api_school_pkey"),
        Index("unique_inep_code", "inep_code", unique=True),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(120))
    user_submitted: Mapped[bool] = mapped_column(Boolean)
    inep_code: Mapped[str] = mapped_column(String(40))

    api_user: Mapped[List["ApiUser"]] = relationship("ApiUser", back_populates="school")


class AuthGroup(Base):
    __tablename__ = "auth_group"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="auth_group_pkey"),
        UniqueConstraint("name", name="auth_group_name_key"),
        Index("auth_group_name_a6ea08ec_like", "name"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(150))

    api_user_groups: Mapped[List["ApiUserGroups"]] = relationship(
        "ApiUserGroups", back_populates="group"
    )
    auth_group_permissions: Mapped[List["AuthGroupPermissions"]] = relationship(
        "AuthGroupPermissions", back_populates="group"
    )


class BonusEventsBonusevent(Base):
    __tablename__ = "bonus_events_bonusevent"
    __table_args__ = (PrimaryKeyConstraint("id", name="bonus_events_bonusevent_pkey"),)

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(255))
    multiplier: Mapped[float] = mapped_column(Double(53))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    start_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    end_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    bonus_events_bonusevent_challenges: Mapped[
        List["BonusEventsBonuseventChallenges"]
    ] = relationship("BonusEventsBonuseventChallenges", back_populates="bonusevent")
    bonus_events_bonusevent_sessions: Mapped[List["BonusEventsBonuseventSessions"]] = (
        relationship("BonusEventsBonuseventSessions", back_populates="bonusevent")
    )


class ChallengesChallenge(Base):
    __tablename__ = "challenges_challenge"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="challenges_challenge_pkey"),
        UniqueConstraint("code", name="challenges_challenge_code_key"),
        Index("challenges_challenge_code_b7c1235b_like", "code"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    code: Mapped[str] = mapped_column(String(5))
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    start_date: Mapped[datetime.date] = mapped_column(Date)
    end_date: Mapped[datetime.date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(255))
    scoring_system: Mapped[str] = mapped_column(String(12))
    questions_per_day: Mapped[Optional[int]] = mapped_column(Integer)

    bonus_events_bonusevent_challenges: Mapped[
        List["BonusEventsBonuseventChallenges"]
    ] = relationship("BonusEventsBonuseventChallenges", back_populates="challenge")
    challenges_challengeparticipation: Mapped[
        List["ChallengesChallengeparticipation"]
    ] = relationship("ChallengesChallengeparticipation", back_populates="challenge")


class ChallengesTournament(Base):
    __tablename__ = "challenges_tournament"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="challenges_tournament_pkey"),
        UniqueConstraint("code", name="challenges_tournament_code_key"),
        Index("challenges_tournament_code_cc224add_like", "code"),
    )

    code: Mapped[str] = mapped_column(String(5))
    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    start_time: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    end_time: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    status: Mapped[str] = mapped_column(String(12))

    quiz_session: Mapped[List["QuizSession"]] = relationship(
        "QuizSession", back_populates="tournament"
    )
    challenges_prize: Mapped[List["ChallengesPrize"]] = relationship(
        "ChallengesPrize", back_populates="tournament"
    )
    challenges_tournamentparticipation: Mapped[
        List["ChallengesTournamentparticipation"]
    ] = relationship("ChallengesTournamentparticipation", back_populates="tournament")


class DjangoContentType(Base):
    __tablename__ = "django_content_type"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="django_content_type_pkey"),
        UniqueConstraint(
            "app_label",
            "model",
            name="django_content_type_app_label_model_76bd3d3b_uniq",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    app_label: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))

    auth_permission: Mapped[List["AuthPermission"]] = relationship(
        "AuthPermission", back_populates="content_type"
    )
    currency_currency: Mapped[List["CurrencyCurrency"]] = relationship(
        "CurrencyCurrency", back_populates="content_type"
    )
    currency_transaction: Mapped[List["CurrencyTransaction"]] = relationship(
        "CurrencyTransaction", back_populates="content_type"
    )
    django_admin_log: Mapped[List["DjangoAdminLog"]] = relationship(
        "DjangoAdminLog", back_populates="content_type"
    )


class DjangoMigrations(Base):
    __tablename__ = "django_migrations"
    __table_args__ = (PrimaryKeyConstraint("id", name="django_migrations_pkey"),)

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    app: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    applied: Mapped[datetime.datetime] = mapped_column(DateTime(True))


class DjangoSession(Base):
    __tablename__ = "django_session"
    __table_args__ = (
        PrimaryKeyConstraint("session_key", name="django_session_pkey"),
        Index("django_session_expire_date_a5c62663", "expire_date"),
        Index("django_session_session_key_c0390e0f_like", "session_key"),
    )

    session_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    session_data: Mapped[str] = mapped_column(Text)
    expire_date: Mapped[datetime.datetime] = mapped_column(DateTime(True))


class DjangoSite(Base):
    __tablename__ = "django_site"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="django_site_pkey"),
        UniqueConstraint("domain", name="django_site_domain_a2e37b91_uniq"),
        Index("django_site_domain_a2e37b91_like", "domain"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    domain: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(50))


class EssaysEssaytopic(Base):
    __tablename__ = "essays_essaytopic"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="essays_essaytopic_pkey"),
        UniqueConstraint("name", name="essays_essaytopic_name_key"),
        Index("essays_essaytopic_name_347883d9_like", "name"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True))

    api_message: Mapped[List["ApiMessage"]] = relationship(
        "ApiMessage", back_populates="essay_topic"
    )
    essays_essay: Mapped[List["EssaysEssay"]] = relationship(
        "EssaysEssay", back_populates="essay_topic"
    )


class EssaysEssaytype(Base):
    __tablename__ = "essays_essaytype"
    __table_args__ = (
        PrimaryKeyConstraint("name", name="essays_essaytype_pkey"),
        Index("essays_essaytype_name_e82cfb99_like", "name"),
    )

    name: Mapped[str] = mapped_column(String(255), primary_key=True)

    essays_feedbackcategory: Mapped[List["EssaysFeedbackcategory"]] = relationship(
        "EssaysFeedbackcategory", back_populates="essay_type"
    )
    essays_essay: Mapped[List["EssaysEssay"]] = relationship(
        "EssaysEssay", back_populates="essay_type"
    )


class QuizQuestion(Base):
    __tablename__ = "quiz_question"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="quiz_question_pkey"),
        Index("new_question_embedding_index", "embedding"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    subject: Mapped[str] = mapped_column(String(255))
    extra_embedding_text: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    image: Mapped[str] = mapped_column(String(100))
    answer_text: Mapped[str] = mapped_column(Text)
    answer_image: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    caderno: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean)
    difficulty: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(100))
    subcategory: Mapped[str] = mapped_column(String(100))
    allow_resubmit: Mapped[bool] = mapped_column(Boolean)
    video_url: Mapped[str] = mapped_column(String(200))
    is_fast: Mapped[bool] = mapped_column(Boolean)
    embedding: Mapped[Optional[Any]] = mapped_column(VECTOR(1024))
    caderno_number: Mapped[Optional[int]] = mapped_column(Integer)
    parameter_A: Mapped[Optional[float]] = mapped_column(Double(53))
    parameter_B: Mapped[Optional[float]] = mapped_column(Double(53))
    parameter_C: Mapped[Optional[float]] = mapped_column(Double(53))

    quiz_choice: Mapped[List["QuizChoice"]] = relationship(
        "QuizChoice", back_populates="question"
    )
    quiz_sessionquestion: Mapped[List["QuizSessionquestion"]] = relationship(
        "QuizSessionquestion", back_populates="question"
    )


class QuizRound(Base):
    __tablename__ = "quiz_round"
    __table_args__ = (
        ForeignKeyConstraint(
            ["duel_id"],
            ["quiz_session.id"],
            deferrable=True,
            initially="DEFERRED",
            name="quiz_round_duel_id_934bd7e9_fk_quiz_session_id",
        ),
        PrimaryKeyConstraint("id", name="quiz_round_pkey"),
        Index("quiz_round_duel_id_934bd7e9", "duel_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    query: Mapped[str] = mapped_column(Text)
    duel_id: Mapped[int] = mapped_column(BigInteger)
    _order: Mapped[int] = mapped_column(Integer)

    duel: Mapped["QuizSession"] = relationship(
        "QuizSession", back_populates="quiz_round"
    )
    quiz_turn: Mapped[List["QuizTurn"]] = relationship(
        "QuizTurn", back_populates="round"
    )


class QuizSession(Base):
    __tablename__ = "quiz_session"
    __table_args__ = (
        CheckConstraint(
            "(duel_status::text = ANY (ARRAY['in_progress'::character varying, 'completed'::character varying, 'abandoned'::character varying]::text[])) AND n_questions_per_round IS NOT NULL AND session_type::text = 'duel'::text OR NOT session_type::text = 'duel'::text",
            name="duel_required_fields_valid",
        ),
        CheckConstraint(
            "(question_type::text = ANY (ARRAY['multiple_choice'::character varying, 'open_ended'::character varying, 'all'::character varying]::text[])) AND session_type::text = 'quiz'::text OR NOT session_type::text = 'quiz'::text",
            name="quiz_question_type_valid",
        ),
        CheckConstraint(
            "(quiz_type::text = ANY (ARRAY['query'::character varying, 'personalized'::character varying, 'custom'::character varying]::text[])) AND session_type::text = 'quiz'::text OR NOT session_type::text = 'quiz'::text",
            name="quiz_quiz_type_valid",
        ),
        CheckConstraint(
            "NOT (session_type::text = ANY (ARRAY['duel'::character varying, 'challenge'::character varying]::text[])) AND selection_method::text = ''::text OR (session_type::text = ANY (ARRAY['duel'::character varying, 'challenge'::character varying]::text[]))",
            name="non_duel_challenge_selection_method_valid",
        ),
        CheckConstraint(
            "NOT session_type::text = 'duel'::text AND current_turn_id IS NULL AND duel_status::text = ''::text AND n_questions_per_round IS NULL AND tournament_id IS NULL AND winner_id IS NULL OR session_type::text = 'duel'::text",
            name="duel_non_applicable_fields_null",
        ),
        CheckConstraint(
            "end_time IS NOT NULL AND session_type::text = 'challenge'::text AND start_time IS NOT NULL OR NOT session_type::text = 'challenge'::text",
            name="challenge_start_end_time_valid",
        ),
        CheckConstraint(
            "selection_method::text = ANY (ARRAY['random_official'::character varying, 'query_official'::character varying, 'user_generated'::character varying]::text[])) AND (session_type::text = ANY (ARRAY['duel'::character varying, 'challenge'::character varying]::text[])) OR NOT (session_type::text = ANY (ARRAY['duel'::character varying, 'challenge'::character varying]::text[])",
            name="duel_challenge_selection_method_valid",
        ),
        ForeignKeyConstraint(
            ["created_by_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="quiz_session_created_by_id_08a15086_fk_api_user_id",
        ),
        ForeignKeyConstraint(
            ["current_turn_id"],
            ["quiz_turn.id"],
            deferrable=True,
            initially="DEFERRED",
            name="quiz_session_current_turn_id_15812595_fk_quiz_turn_id",
        ),
        ForeignKeyConstraint(
            ["parent_session_id"],
            ["quiz_session.id"],
            deferrable=True,
            initially="DEFERRED",
            name="quiz_session_parent_session_id_a02429bd_fk_quiz_session_id",
        ),
        ForeignKeyConstraint(
            ["tournament_id"],
            ["challenges_tournament.id"],
            deferrable=True,
            initially="DEFERRED",
            name="quiz_session_tournament_id_ca5ca69b_fk_challenges_tournament_id",
        ),
        ForeignKeyConstraint(
            ["winner_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="quiz_session_winner_id_b37d187d_fk_api_user_id",
        ),
        PrimaryKeyConstraint("id", name="quiz_session_pkey"),
        UniqueConstraint("code", name="quiz_session_code_key"),
        Index("quiz_session_code_986bc66d_like", "code"),
        Index("quiz_session_created_by_id_08a15086", "created_by_id"),
        Index("quiz_session_current_turn_id_15812595", "current_turn_id"),
        Index("quiz_session_parent_session_id_a02429bd", "parent_session_id"),
        Index("quiz_session_tournament_id_ca5ca69b", "tournament_id"),
        Index("quiz_session_winner_id_b37d187d", "winner_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    session_type: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    query: Mapped[str] = mapped_column(Text)
    area: Mapped[str] = mapped_column(String(255))
    source_filter: Mapped[str] = mapped_column(String(255))
    difficulty: Mapped[str] = mapped_column(String(50))
    question_type: Mapped[str] = mapped_column(String(16))
    quiz_type: Mapped[str] = mapped_column(String(16))
    file: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(5))
    selection_method: Mapped[str] = mapped_column(String(25))
    duel_status: Mapped[str] = mapped_column(String(25))
    is_fast: Mapped[bool] = mapped_column(Boolean)
    title: Mapped[str] = mapped_column(String(255))
    created_by_id: Mapped[Optional[int]] = mapped_column(Integer)
    parent_session_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    n_questions_per_round: Mapped[Optional[int]] = mapped_column(Integer)
    winner_id: Mapped[Optional[int]] = mapped_column(Integer)
    tournament_id: Mapped[Optional[int]] = mapped_column(Integer)
    end_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    start_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    current_turn_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    quiz_round: Mapped[List["QuizRound"]] = relationship(
        "QuizRound", back_populates="duel"
    )
    created_by: Mapped[Optional["ApiUser"]] = relationship(
        "ApiUser", foreign_keys=[created_by_id], back_populates="quiz_session"
    )
    current_turn: Mapped[Optional["QuizTurn"]] = relationship(
        "QuizTurn", back_populates="quiz_session"
    )
    parent_session: Mapped[Optional["QuizSession"]] = relationship(
        "QuizSession", remote_side=[id], back_populates="parent_session_reverse"
    )
    parent_session_reverse: Mapped[List["QuizSession"]] = relationship(
        "QuizSession", remote_side=[parent_session_id], back_populates="parent_session"
    )
    tournament: Mapped[Optional["ChallengesTournament"]] = relationship(
        "ChallengesTournament", back_populates="quiz_session"
    )
    winner: Mapped[Optional["ApiUser"]] = relationship(
        "ApiUser", foreign_keys=[winner_id], back_populates="quiz_session_"
    )
    bonus_events_bonusevent_sessions: Mapped[List["BonusEventsBonuseventSessions"]] = (
        relationship("BonusEventsBonuseventSessions", back_populates="session")
    )
    quiz_sessionquestion: Mapped[List["QuizSessionquestion"]] = relationship(
        "QuizSessionquestion", back_populates="session"
    )
    api_message: Mapped[List["ApiMessage"]] = relationship(
        "ApiMessage", back_populates="session"
    )
    quiz_sessionparticipation: Mapped[List["QuizSessionparticipation"]] = relationship(
        "QuizSessionparticipation", back_populates="session"
    )


class QuizTurn(Base):
    __tablename__ = "quiz_turn"
    __table_args__ = (
        ForeignKeyConstraint(
            ["round_id"],
            ["quiz_round.id"],
            deferrable=True,
            initially="DEFERRED",
            name="quiz_turn_round_id_f1163bac_fk_quiz_round_id",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="quiz_turn_user_id_0e278150_fk_api_user_id",
        ),
        PrimaryKeyConstraint("id", name="quiz_turn_pkey"),
        UniqueConstraint("round_id", "user_id", name="unique_turn_per_round_and_user"),
        Index("quiz_turn_round_id_f1163bac", "round_id"),
        Index("quiz_turn_user_id_0e278150", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    phase: Mapped[str] = mapped_column(String(25))
    round_id: Mapped[int] = mapped_column(BigInteger)
    _order: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    user_id: Mapped[Optional[int]] = mapped_column(Integer)

    quiz_session: Mapped[List["QuizSession"]] = relationship(
        "QuizSession", back_populates="current_turn"
    )
    round: Mapped["QuizRound"] = relationship("QuizRound", back_populates="quiz_turn")
    user: Mapped[Optional["ApiUser"]] = relationship(
        "ApiUser", back_populates="quiz_turn"
    )


class ApiCollegeCourses(Base):
    __tablename__ = "api_college_courses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["college_id"],
            ["api_college.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_college_courses_college_id_01d49191_fk_api_college_id",
        ),
        ForeignKeyConstraint(
            ["course_id"],
            ["api_course.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_college_courses_course_id_ea984a76_fk_api_course_id",
        ),
        PrimaryKeyConstraint("id", name="api_college_courses_pkey"),
        UniqueConstraint(
            "college_id",
            "course_id",
            name="api_college_courses_college_id_course_id_588453a0_uniq",
        ),
        Index("api_college_courses_college_id_01d49191", "college_id"),
        Index("api_college_courses_course_id_ea984a76", "course_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    college_id: Mapped[int] = mapped_column(Integer)
    course_id: Mapped[int] = mapped_column(Integer)

    college: Mapped["ApiCollege"] = relationship(
        "ApiCollege", back_populates="api_college_courses"
    )
    course: Mapped["ApiCourse"] = relationship(
        "ApiCourse", back_populates="api_college_courses"
    )


class ApiEmbeddedfile(Base):
    __tablename__ = "api_embeddedfile"
    __table_args__ = (
        ForeignKeyConstraint(
            ["file_group_id"],
            ["api_filegroup.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_embeddedfile_file_group_id_fc7447ec_fk_api_filegroup_id",
        ),
        PrimaryKeyConstraint("id", name="api_embeddedfile_pkey"),
        Index("api_embeddedfile_file_group_id_fc7447ec", "file_group_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    file: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text)
    file_processing_done: Mapped[Optional[bool]] = mapped_column(Boolean)
    file_group_id: Mapped[Optional[int]] = mapped_column(Integer)

    file_group: Mapped[Optional["ApiFilegroup"]] = relationship(
        "ApiFilegroup", back_populates="api_embeddedfile"
    )
    api_embeddedtextchunk: Mapped[List["ApiEmbeddedtextchunk"]] = relationship(
        "ApiEmbeddedtextchunk", back_populates="embedded_file"
    )
    api_embeddedfile_messages: Mapped[List["ApiEmbeddedfileMessages"]] = relationship(
        "ApiEmbeddedfileMessages", back_populates="embeddedfile"
    )


class ApiUser(Base):
    __tablename__ = "api_user"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="api_user_balance_check"),
        CheckConstraint(
            "bot_difficulty IS NOT NULL AND is_bot OR bot_difficulty IS NULL AND NOT is_bot",
            name="bot_difficulty_validation",
        ),
        ForeignKeyConstraint(
            ["chosen_college_id"],
            ["api_college.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_user_chosen_college_id_29a6a472_fk_api_college_id",
        ),
        ForeignKeyConstraint(
            ["chosen_course_id"],
            ["api_course.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_user_chosen_course_id_4d963b51_fk_api_course_id",
        ),
        ForeignKeyConstraint(
            ["referred_by_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_user_referred_by_id_a851dc47_fk_api_user_id",
        ),
        ForeignKeyConstraint(
            ["school_id"],
            ["api_school.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_user_school_id_baa2f41b_fk_api_school_id",
        ),
        PrimaryKeyConstraint("id", name="api_user_pkey"),
        UniqueConstraint("email", name="api_user_email_key"),
        UniqueConstraint("phone_number", name="api_user_phone_number_key"),
        UniqueConstraint("username", name="api_user_username_key"),
        Index("api_user_chosen_college_id_29a6a472", "chosen_college_id"),
        Index("api_user_chosen_course_id_4d963b51", "chosen_course_id"),
        Index("api_user_email_9ef5afa6_like", "email"),
        Index("api_user_phone_number_7fd8ad9a_like", "phone_number"),
        Index("api_user_referred_by_id_a851dc47", "referred_by_id"),
        Index("api_user_school_id_baa2f41b", "school_id"),
        Index("api_user_username_cf4e88d2_like", "username"),
    )

    password: Mapped[str] = mapped_column(String(128))
    is_superuser: Mapped[bool] = mapped_column(Boolean)
    first_name: Mapped[str] = mapped_column(String(150))
    last_name: Mapped[str] = mapped_column(String(150))
    is_staff: Mapped[bool] = mapped_column(Boolean)
    is_active: Mapped[bool] = mapped_column(Boolean)
    date_joined: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    username: Mapped[str] = mapped_column(String(50))
    phone_number: Mapped[str] = mapped_column(String(25))
    email: Mapped[str] = mapped_column(String(255))
    is_premium: Mapped[bool] = mapped_column(Boolean)
    commitment: Mapped[int] = mapped_column(Integer)
    education_level: Mapped[str] = mapped_column(String(4))
    balance: Mapped[int] = mapped_column(Integer)
    is_bot: Mapped[bool] = mapped_column(Boolean)
    signup_source: Mapped[str] = mapped_column(String(255))
    last_login: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    chosen_college_id: Mapped[Optional[int]] = mapped_column(Integer)
    chosen_course_id: Mapped[Optional[int]] = mapped_column(Integer)
    referred_by_id: Mapped[Optional[int]] = mapped_column(Integer)
    bot_difficulty: Mapped[Optional[float]] = mapped_column(Double(53))
    school_id: Mapped[Optional[int]] = mapped_column(Integer)

    quiz_session: Mapped[List["QuizSession"]] = relationship(
        "QuizSession",
        foreign_keys="[QuizSession.created_by_id]",
        back_populates="created_by",
    )
    quiz_session_: Mapped[List["QuizSession"]] = relationship(
        "QuizSession", foreign_keys="[QuizSession.winner_id]", back_populates="winner"
    )
    quiz_turn: Mapped[List["QuizTurn"]] = relationship(
        "QuizTurn", back_populates="user"
    )
    chosen_college: Mapped[Optional["ApiCollege"]] = relationship(
        "ApiCollege", back_populates="api_user"
    )
    chosen_course: Mapped[Optional["ApiCourse"]] = relationship(
        "ApiCourse", back_populates="api_user"
    )
    referred_by: Mapped[Optional["ApiUser"]] = relationship(
        "ApiUser", remote_side=[id], back_populates="referred_by_reverse"
    )
    referred_by_reverse: Mapped[List["ApiUser"]] = relationship(
        "ApiUser", remote_side=[referred_by_id], back_populates="referred_by"
    )
    school: Mapped[Optional["ApiSchool"]] = relationship(
        "ApiSchool", back_populates="api_user"
    )
    api_membership: Mapped[List["ApiMembership"]] = relationship(
        "ApiMembership", back_populates="user"
    )
    api_message: Mapped[List["ApiMessage"]] = relationship(
        "ApiMessage", back_populates="sender"
    )
    api_user_groups: Mapped[List["ApiUserGroups"]] = relationship(
        "ApiUserGroups", back_populates="user"
    )
    api_user_user_permissions: Mapped[List["ApiUserUserPermissions"]] = relationship(
        "ApiUserUserPermissions", back_populates="user"
    )
    challenges_challengeparticipation: Mapped[
        List["ChallengesChallengeparticipation"]
    ] = relationship("ChallengesChallengeparticipation", back_populates="user")
    challenges_tournamentparticipation: Mapped[
        List["ChallengesTournamentparticipation"]
    ] = relationship("ChallengesTournamentparticipation", back_populates="user")
    chat_userwebsocketinfo: Mapped["ChatUserwebsocketinfo"] = relationship(
        "ChatUserwebsocketinfo", uselist=False, back_populates="user"
    )
    currency_transaction: Mapped[List["CurrencyTransaction"]] = relationship(
        "CurrencyTransaction", back_populates="user"
    )
    django_admin_log: Mapped[List["DjangoAdminLog"]] = relationship(
        "DjangoAdminLog", back_populates="user"
    )
    essays_essay: Mapped[List["EssaysEssay"]] = relationship(
        "EssaysEssay", back_populates="author"
    )
    fcm_django_fcmdevice: Mapped[List["FcmDjangoFcmdevice"]] = relationship(
        "FcmDjangoFcmdevice", back_populates="user"
    )
    quiz_sessionparticipation: Mapped[List["QuizSessionparticipation"]] = relationship(
        "QuizSessionparticipation", back_populates="user"
    )
    quiz_sessionquestionuser: Mapped[List["QuizSessionquestionuser"]] = relationship(
        "QuizSessionquestionuser", back_populates="user"
    )
    quiz_userinfo: Mapped["QuizUserinfo"] = relationship(
        "QuizUserinfo", uselist=False, back_populates="user"
    )
    study_plans_studyplan: Mapped[List["StudyPlansStudyplan"]] = relationship(
        "StudyPlansStudyplan", back_populates="user"
    )


class AuthPermission(Base):
    __tablename__ = "auth_permission"
    __table_args__ = (
        ForeignKeyConstraint(
            ["content_type_id"],
            ["django_content_type.id"],
            deferrable=True,
            initially="DEFERRED",
            name="auth_permission_content_type_id_2f476e4b_fk_django_co",
        ),
        PrimaryKeyConstraint("id", name="auth_permission_pkey"),
        UniqueConstraint(
            "content_type_id",
            "codename",
            name="auth_permission_content_type_id_codename_01ab375a_uniq",
        ),
        Index("auth_permission_content_type_id_2f476e4b", "content_type_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(255))
    content_type_id: Mapped[int] = mapped_column(Integer)
    codename: Mapped[str] = mapped_column(String(100))

    content_type: Mapped["DjangoContentType"] = relationship(
        "DjangoContentType", back_populates="auth_permission"
    )
    api_user_user_permissions: Mapped[List["ApiUserUserPermissions"]] = relationship(
        "ApiUserUserPermissions", back_populates="permission"
    )
    auth_group_permissions: Mapped[List["AuthGroupPermissions"]] = relationship(
        "AuthGroupPermissions", back_populates="permission"
    )


class BonusEventsBonuseventChallenges(Base):
    __tablename__ = "bonus_events_bonusevent_challenges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["bonusevent_id"],
            ["bonus_events_bonusevent.id"],
            deferrable=True,
            initially="DEFERRED",
            name="bonus_events_bonusev_bonusevent_id_96f90320_fk_bonus_eve",
        ),
        ForeignKeyConstraint(
            ["challenge_id"],
            ["challenges_challenge.id"],
            deferrable=True,
            initially="DEFERRED",
            name="bonus_events_bonusev_challenge_id_e6e48290_fk_challenge",
        ),
        PrimaryKeyConstraint("id", name="bonus_events_bonusevent_challenges_pkey"),
        UniqueConstraint(
            "bonusevent_id",
            "challenge_id",
            name="bonus_events_bonusevent__bonusevent_id_challenge__eb12f3f8_uniq",
        ),
        Index(
            "bonus_events_bonusevent_challenges_bonusevent_id_96f90320", "bonusevent_id"
        ),
        Index(
            "bonus_events_bonusevent_challenges_challenge_id_e6e48290", "challenge_id"
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    bonusevent_id: Mapped[int] = mapped_column(BigInteger)
    challenge_id: Mapped[int] = mapped_column(Integer)

    bonusevent: Mapped["BonusEventsBonusevent"] = relationship(
        "BonusEventsBonusevent", back_populates="bonus_events_bonusevent_challenges"
    )
    challenge: Mapped["ChallengesChallenge"] = relationship(
        "ChallengesChallenge", back_populates="bonus_events_bonusevent_challenges"
    )


class BonusEventsBonuseventSessions(Base):
    __tablename__ = "bonus_events_bonusevent_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["bonusevent_id"],
            ["bonus_events_bonusevent.id"],
            deferrable=True,
            initially="DEFERRED",
            name="bonus_events_bonusev_bonusevent_id_3a91b7fb_fk_bonus_eve",
        ),
        ForeignKeyConstraint(
            ["session_id"],
            ["quiz_session.id"],
            deferrable=True,
            initially="DEFERRED",
            name="bonus_events_bonusev_session_id_ba9d6738_fk_quiz_sess",
        ),
        PrimaryKeyConstraint("id", name="bonus_events_bonusevent_sessions_pkey"),
        UniqueConstraint(
            "bonusevent_id",
            "session_id",
            name="bonus_events_bonusevent__bonusevent_id_session_id_2768ebef_uniq",
        ),
        Index(
            "bonus_events_bonusevent_sessions_bonusevent_id_3a91b7fb", "bonusevent_id"
        ),
        Index("bonus_events_bonusevent_sessions_session_id_ba9d6738", "session_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    bonusevent_id: Mapped[int] = mapped_column(BigInteger)
    session_id: Mapped[int] = mapped_column(BigInteger)

    bonusevent: Mapped["BonusEventsBonusevent"] = relationship(
        "BonusEventsBonusevent", back_populates="bonus_events_bonusevent_sessions"
    )
    session: Mapped["QuizSession"] = relationship(
        "QuizSession", back_populates="bonus_events_bonusevent_sessions"
    )


class ChallengesPrize(Base):
    __tablename__ = "challenges_prize"
    __table_args__ = (
        CheckConstraint("rank >= 0", name="challenges_prize_rank_check"),
        ForeignKeyConstraint(
            ["tournament_id"],
            ["challenges_tournament.id"],
            deferrable=True,
            initially="DEFERRED",
            name="challenges_prize_tournament_id_9b5d67cf_fk_challenge",
        ),
        PrimaryKeyConstraint("id", name="challenges_prize_pkey"),
        UniqueConstraint("tournament_id", "rank", name="unique_prize_rank"),
        Index("challenges_prize_tournament_id_9b5d67cf", "tournament_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    rank: Mapped[int] = mapped_column(Integer)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2))
    tournament_id: Mapped[int] = mapped_column(Integer)

    tournament: Mapped["ChallengesTournament"] = relationship(
        "ChallengesTournament", back_populates="challenges_prize"
    )


class CurrencyCurrency(Base):
    __tablename__ = "currency_currency"
    __table_args__ = (
        CheckConstraint(
            "action::text = ANY (ARRAY['user_referred_another'::character varying, 'another_user_referred_me'::character varying, 'dynamic_ranking_reward'::character varying, 'school_dynamic_ranking_reward'::character varying, 'custom_quiz_creation'::character varying, 'custom_quiz_join'::character varying, 'quiz_creation'::character varying, 'quiz_join'::character varying, 'custom_duel_creation'::character varying, 'custom_duel_join'::character varying, 'duel_creation'::character varying, 'duel_join'::character varying, 'essay_creation'::character varying, 'custom_challenge_creation'::character varying, 'custom_challenge_join'::character varying, 'custom_challenge_commission'::character varying, 'challenge_creation'::character varying, 'challenge_join'::character varying, 'challenge_commission'::character varying]::text[])",
            name="valid_currency_action",
        ),
        CheckConstraint("object_id >= 0", name="currency_currency_object_id_check"),
        CheckConstraint("value >= 0", name="currency_currency_amount_check"),
        ForeignKeyConstraint(
            ["content_type_id"],
            ["django_content_type.id"],
            deferrable=True,
            initially="DEFERRED",
            name="currency_currency_content_type_id_c13d926d_fk_django_co",
        ),
        PrimaryKeyConstraint("id", name="currency_currency_pkey"),
        Index("currency_currency_content_type_id_c13d926d", "content_type_id"),
        Index(
            "unique_default_currency_per_action_type",
            "action",
            "currency_type",
            "is_default",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    value: Mapped[int] = mapped_column(Integer)
    currency_type: Mapped[str] = mapped_column(String(10))
    is_default: Mapped[bool] = mapped_column(Boolean)
    description: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    action: Mapped[str] = mapped_column(String(50))
    object_id: Mapped[Optional[int]] = mapped_column(Integer)
    content_type_id: Mapped[Optional[int]] = mapped_column(Integer)

    content_type: Mapped[Optional["DjangoContentType"]] = relationship(
        "DjangoContentType", back_populates="currency_currency"
    )
    currency_transaction: Mapped[List["CurrencyTransaction"]] = relationship(
        "CurrencyTransaction", back_populates="currency"
    )


class EssaysFeedbackcategory(Base):
    __tablename__ = "essays_feedbackcategory"
    __table_args__ = (
        ForeignKeyConstraint(
            ["essay_type_id"],
            ["essays_essaytype.name"],
            deferrable=True,
            initially="DEFERRED",
            name="essays_feedbackcateg_essay_type_id_32641a90_fk_essays_es",
        ),
        PrimaryKeyConstraint("id", name="essays_feedbackcategory_pkey"),
        Index("essays_feedbackcategory_essay_type_id_32641a90", "essay_type_id"),
        Index("essays_feedbackcategory_essay_type_id_32641a90_like", "essay_type_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(255))
    prompt_template: Mapped[str] = mapped_column(Text)
    temperature: Mapped[float] = mapped_column(Double(53))
    essay_type_id: Mapped[str] = mapped_column(String(255))

    essay_type: Mapped["EssaysEssaytype"] = relationship(
        "EssaysEssaytype", back_populates="essays_feedbackcategory"
    )
    essays_feedback: Mapped[List["EssaysFeedback"]] = relationship(
        "EssaysFeedback", back_populates="feedback_category"
    )


class QuizChoice(Base):
    __tablename__ = "quiz_choice"
    __table_args__ = (
        CheckConstraint(
            "NOT image::text = ''::text AND text = ''::text OR image::text = ''::text AND NOT text = ''::text",
            name="choice_has_image_xor_text",
        ),
        ForeignKeyConstraint(
            ["question_id"],
            ["quiz_question.id"],
            deferrable=True,
            initially="DEFERRED",
            name="quiz_choice_question_id_6297ad3f_fk_quiz_question_id",
        ),
        PrimaryKeyConstraint("id", name="quiz_choice_pkey"),
        Index("quiz_choice_question_id_6297ad3f", "question_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    text: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    question_id: Mapped[int] = mapped_column(BigInteger)
    _order: Mapped[int] = mapped_column(Integer)
    image: Mapped[str] = mapped_column(String(100))

    question: Mapped["QuizQuestion"] = relationship(
        "QuizQuestion", back_populates="quiz_choice"
    )
    quiz_sessionquestionuser: Mapped[List["QuizSessionquestionuser"]] = relationship(
        "QuizSessionquestionuser", back_populates="choice"
    )


class QuizSessionquestion(Base):
    __tablename__ = "quiz_sessionquestion"
    __table_args__ = (
        CheckConstraint('"order" >= 0', name="quiz_sessionquestion_order_check"),
        ForeignKeyConstraint(
            ["question_id"],
            ["quiz_question.id"],
            deferrable=True,
            initially="DEFERRED",
            name="quiz_sessionquestion_question_id_e8dc5a47_fk_quiz_question_id",
        ),
        ForeignKeyConstraint(
            ["session_id"],
            ["quiz_session.id"],
            deferrable=True,
            initially="DEFERRED",
            name="quiz_sessionquestion_session_id_8f79bcaa_fk_quiz_session_id",
        ),
        PrimaryKeyConstraint("id", name="quiz_sessionquestion_pkey"),
        UniqueConstraint(
            "session_id",
            "question_id",
            name="quiz_sessionquestion_session_id_question_id_b757453e_uniq",
        ),
        Index("quiz_sessionquestion_order_d5dab18c", "order"),
        Index("quiz_sessionquestion_question_id_e8dc5a47", "question_id"),
        Index("quiz_sessionquestion_session_id_8f79bcaa", "session_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    order: Mapped[int] = mapped_column(Integer)
    question_id: Mapped[int] = mapped_column(BigInteger)
    session_id: Mapped[int] = mapped_column(BigInteger)

    question: Mapped["QuizQuestion"] = relationship(
        "QuizQuestion", back_populates="quiz_sessionquestion"
    )
    session: Mapped["QuizSession"] = relationship(
        "QuizSession", back_populates="quiz_sessionquestion"
    )
    quiz_sessionquestionuser: Mapped[List["QuizSessionquestionuser"]] = relationship(
        "QuizSessionquestionuser", back_populates="session_question"
    )


class ApiEmbeddedtextchunk(Base):
    __tablename__ = "api_embeddedtextchunk"
    __table_args__ = (
        ForeignKeyConstraint(
            ["embedded_file_id"],
            ["api_embeddedfile.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_embeddedtextchun_embedded_file_id_2ab232a2_fk_api_embed",
        ),
        PrimaryKeyConstraint("id", name="api_embeddedtextchunk_pkey"),
        Index("api_embeddedtextchunk_embedded_file_id_2ab232a2", "embedded_file_id"),
        Index("chunk_cosine_similarity_index", "embedding"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    text: Mapped[str] = mapped_column(Text)
    embedded_file_id: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[Optional[Any]] = mapped_column(VECTOR(1024))

    embedded_file: Mapped["ApiEmbeddedfile"] = relationship(
        "ApiEmbeddedfile", back_populates="api_embeddedtextchunk"
    )


class ApiMembership(Base):
    __tablename__ = "api_membership"
    __table_args__ = (
        ForeignKeyConstraint(
            ["chatroom_id"],
            ["api_chatroom.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_membership_chatroom_id_b9e6b7a7_fk_api_chatroom_id",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_membership_user_id_2ab90bda_fk_api_user_id",
        ),
        PrimaryKeyConstraint("id", name="api_membership_pkey"),
        UniqueConstraint("user_id", "chatroom_id", name="unique_membership"),
        Index("api_members_user_id_07b380_idx", "user_id", "chatroom_id"),
        Index("api_membership_chatroom_id_b9e6b7a7", "chatroom_id"),
        Index("api_membership_user_id_2ab90bda", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    chatroom_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(3))

    chatroom: Mapped["ApiChatroom"] = relationship(
        "ApiChatroom", back_populates="api_membership"
    )
    user: Mapped["ApiUser"] = relationship("ApiUser", back_populates="api_membership")


class ApiMessage(Base):
    __tablename__ = "api_message"
    __table_args__ = (
        ForeignKeyConstraint(
            ["chatroom_id"],
            ["api_chatroom.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_message_chatroom_id_1bcdfaba_fk_api_chatroom_id",
        ),
        ForeignKeyConstraint(
            ["essay_topic_id"],
            ["essays_essaytopic.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_message_essay_topic_id_78d1f3ed_fk_essays_essaytopic_id",
        ),
        ForeignKeyConstraint(
            ["parent_message_id"],
            ["api_message.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_message_parent_message_id_3e46aa21_fk_api_message_id",
        ),
        ForeignKeyConstraint(
            ["sender_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_message_sender_id_fa6d8ff2_fk_api_user_id",
        ),
        ForeignKeyConstraint(
            ["session_id"],
            ["quiz_session.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_message_session_id_5d8ba9d9_fk_quiz_session_id",
        ),
        PrimaryKeyConstraint("id", name="api_message_pkey"),
        Index("api_message_chatroo_6c324f_idx", "chatroom_id"),
        Index("api_message_chatroom_id_1bcdfaba", "chatroom_id"),
        Index("api_message_essay_topic_id_78d1f3ed", "essay_topic_id"),
        Index("api_message_parent_message_id_3e46aa21", "parent_message_id"),
        Index("api_message_sender_id_fa6d8ff2", "sender_id"),
        Index("api_message_session_id_5d8ba9d9", "session_id"),
        Index("message_cosine_similarity_index", "embedding"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    chatroom_id: Mapped[int] = mapped_column(Integer)
    sender_id: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[Optional[Any]] = mapped_column(VECTOR(1024))
    parent_message_id: Mapped[Optional[int]] = mapped_column(Integer)
    essay_topic_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    session_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    chatroom: Mapped["ApiChatroom"] = relationship(
        "ApiChatroom", back_populates="api_message"
    )
    essay_topic: Mapped[Optional["EssaysEssaytopic"]] = relationship(
        "EssaysEssaytopic", back_populates="api_message"
    )
    parent_message: Mapped[Optional["ApiMessage"]] = relationship(
        "ApiMessage", remote_side=[id], back_populates="parent_message_reverse"
    )
    parent_message_reverse: Mapped[List["ApiMessage"]] = relationship(
        "ApiMessage", remote_side=[parent_message_id], back_populates="parent_message"
    )
    sender: Mapped["ApiUser"] = relationship("ApiUser", back_populates="api_message")
    session: Mapped[Optional["QuizSession"]] = relationship(
        "QuizSession", back_populates="api_message"
    )
    api_embeddedfile_messages: Mapped[List["ApiEmbeddedfileMessages"]] = relationship(
        "ApiEmbeddedfileMessages", back_populates="message"
    )


class ApiUserGroups(Base):
    __tablename__ = "api_user_groups"
    __table_args__ = (
        ForeignKeyConstraint(
            ["group_id"],
            ["auth_group.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_user_groups_group_id_3af85785_fk_auth_group_id",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_user_groups_user_id_a5ff39fa_fk_api_user_id",
        ),
        PrimaryKeyConstraint("id", name="api_user_groups_pkey"),
        UniqueConstraint(
            "user_id", "group_id", name="api_user_groups_user_id_group_id_9c7ddfb5_uniq"
        ),
        Index("api_user_groups_group_id_3af85785", "group_id"),
        Index("api_user_groups_user_id_a5ff39fa", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(Integer)
    group_id: Mapped[int] = mapped_column(Integer)

    group: Mapped["AuthGroup"] = relationship(
        "AuthGroup", back_populates="api_user_groups"
    )
    user: Mapped["ApiUser"] = relationship("ApiUser", back_populates="api_user_groups")


class ApiUserUserPermissions(Base):
    __tablename__ = "api_user_user_permissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["permission_id"],
            ["auth_permission.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_user_user_permis_permission_id_305b7fea_fk_auth_perm",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_user_user_permissions_user_id_f3945d65_fk_api_user_id",
        ),
        PrimaryKeyConstraint("id", name="api_user_user_permissions_pkey"),
        UniqueConstraint(
            "user_id",
            "permission_id",
            name="api_user_user_permissions_user_id_permission_id_a06dd704_uniq",
        ),
        Index("api_user_user_permissions_permission_id_305b7fea", "permission_id"),
        Index("api_user_user_permissions_user_id_f3945d65", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(Integer)
    permission_id: Mapped[int] = mapped_column(Integer)

    permission: Mapped["AuthPermission"] = relationship(
        "AuthPermission", back_populates="api_user_user_permissions"
    )
    user: Mapped["ApiUser"] = relationship(
        "ApiUser", back_populates="api_user_user_permissions"
    )


class AuthGroupPermissions(Base):
    __tablename__ = "auth_group_permissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["group_id"],
            ["auth_group.id"],
            deferrable=True,
            initially="DEFERRED",
            name="auth_group_permissions_group_id_b120cbf9_fk_auth_group_id",
        ),
        ForeignKeyConstraint(
            ["permission_id"],
            ["auth_permission.id"],
            deferrable=True,
            initially="DEFERRED",
            name="auth_group_permissio_permission_id_84c5c92e_fk_auth_perm",
        ),
        PrimaryKeyConstraint("id", name="auth_group_permissions_pkey"),
        UniqueConstraint(
            "group_id",
            "permission_id",
            name="auth_group_permissions_group_id_permission_id_0cd325b0_uniq",
        ),
        Index("auth_group_permissions_group_id_b120cbf9", "group_id"),
        Index("auth_group_permissions_permission_id_84c5c92e", "permission_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    group_id: Mapped[int] = mapped_column(Integer)
    permission_id: Mapped[int] = mapped_column(Integer)

    group: Mapped["AuthGroup"] = relationship(
        "AuthGroup", back_populates="auth_group_permissions"
    )
    permission: Mapped["AuthPermission"] = relationship(
        "AuthPermission", back_populates="auth_group_permissions"
    )


class ChallengesChallengeparticipation(Base):
    __tablename__ = "challenges_challengeparticipation"
    __table_args__ = (
        ForeignKeyConstraint(
            ["challenge_id"],
            ["challenges_challenge.id"],
            deferrable=True,
            initially="DEFERRED",
            name="challenges_challenge_challenge_id_ec1bda8b_fk_challenge",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="challenges_challenge_user_id_eb628f4a_fk_api_user_",
        ),
        PrimaryKeyConstraint("id", name="challenges_challengeparticipation_pkey"),
        UniqueConstraint("user_id", "challenge_id", name="unique_participation"),
        Index("challenges__user_id_342380_idx", "user_id", "challenge_id"),
        Index(
            "challenges_challengeparticipation_challenge_id_ec1bda8b", "challenge_id"
        ),
        Index("challenges_challengeparticipation_user_id_eb628f4a", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    challenge_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(Integer)

    challenge: Mapped["ChallengesChallenge"] = relationship(
        "ChallengesChallenge", back_populates="challenges_challengeparticipation"
    )
    user: Mapped["ApiUser"] = relationship(
        "ApiUser", back_populates="challenges_challengeparticipation"
    )


class ChallengesTournamentparticipation(Base):
    __tablename__ = "challenges_tournamentparticipation"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tournament_id"],
            ["challenges_tournament.id"],
            deferrable=True,
            initially="DEFERRED",
            name="challenges_tournamen_tournament_id_46b9c569_fk_challenge",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="challenges_tournamen_user_id_95a55b52_fk_api_user_",
        ),
        PrimaryKeyConstraint("id", name="challenges_tournamentparticipation_pkey"),
        UniqueConstraint(
            "user_id", "tournament_id", name="unique_tournament_participation"
        ),
        Index("challenges__user_id_b9f13c_idx", "user_id", "tournament_id"),
        Index(
            "challenges_tournamentparticipation_tournament_id_46b9c569", "tournament_id"
        ),
        Index("challenges_tournamentparticipation_user_id_95a55b52", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    tournament_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(Integer)

    tournament: Mapped["ChallengesTournament"] = relationship(
        "ChallengesTournament", back_populates="challenges_tournamentparticipation"
    )
    user: Mapped["ApiUser"] = relationship(
        "ApiUser", back_populates="challenges_tournamentparticipation"
    )


class ChatUserwebsocketinfo(Base):
    __tablename__ = "chat_userwebsocketinfo"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="chat_userlastconnection_user_id_e9f497c2_fk_api_user_id",
        ),
        PrimaryKeyConstraint("id", name="chat_userlastconnection_pkey"),
        UniqueConstraint("user_id", name="chat_userlastconnection_user_id_key"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    last_websocket_connection: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    user_id: Mapped[int] = mapped_column(Integer)
    last_websocket_disconnection: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(True)
    )

    user: Mapped["ApiUser"] = relationship(
        "ApiUser", back_populates="chat_userwebsocketinfo"
    )


class CurrencyTransaction(Base):
    __tablename__ = "currency_transaction"
    __table_args__ = (
        CheckConstraint("object_id >= 0", name="currency_transaction_object_id_check"),
        ForeignKeyConstraint(
            ["content_type_id"],
            ["django_content_type.id"],
            deferrable=True,
            initially="DEFERRED",
            name="currency_transaction_content_type_id_d8914f65_fk_django_co",
        ),
        ForeignKeyConstraint(
            ["currency_id"],
            ["currency_currency.id"],
            deferrable=True,
            initially="DEFERRED",
            name="currency_transaction_currency_id_20b798d0_fk_currency_",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="currency_transaction_user_id_708256ed_fk_api_user_id",
        ),
        PrimaryKeyConstraint("id", name="currency_transaction_pkey"),
        Index("currency_transaction_content_type_id_d8914f65", "content_type_id"),
        Index("currency_transaction_currency_id_20b798d0", "currency_id"),
        Index("currency_transaction_user_id_708256ed", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    user_id: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(255))
    object_id: Mapped[Optional[int]] = mapped_column(Integer)
    content_type_id: Mapped[Optional[int]] = mapped_column(Integer)
    currency_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    amount: Mapped[Optional[int]] = mapped_column(Integer)

    content_type: Mapped[Optional["DjangoContentType"]] = relationship(
        "DjangoContentType", back_populates="currency_transaction"
    )
    currency: Mapped[Optional["CurrencyCurrency"]] = relationship(
        "CurrencyCurrency", back_populates="currency_transaction"
    )
    user: Mapped["ApiUser"] = relationship(
        "ApiUser", back_populates="currency_transaction"
    )


class DjangoAdminLog(Base):
    __tablename__ = "django_admin_log"
    __table_args__ = (
        CheckConstraint("action_flag >= 0", name="django_admin_log_action_flag_check"),
        ForeignKeyConstraint(
            ["content_type_id"],
            ["django_content_type.id"],
            deferrable=True,
            initially="DEFERRED",
            name="django_admin_log_content_type_id_c4bce8eb_fk_django_co",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="django_admin_log_user_id_c564eba6_fk_api_user_id",
        ),
        PrimaryKeyConstraint("id", name="django_admin_log_pkey"),
        Index("django_admin_log_content_type_id_c4bce8eb", "content_type_id"),
        Index("django_admin_log_user_id_c564eba6", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    action_time: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    object_repr: Mapped[str] = mapped_column(String(200))
    action_flag: Mapped[int] = mapped_column(SmallInteger)
    change_message: Mapped[str] = mapped_column(Text)
    user_id: Mapped[int] = mapped_column(Integer)
    object_id: Mapped[Optional[str]] = mapped_column(Text)
    content_type_id: Mapped[Optional[int]] = mapped_column(Integer)

    content_type: Mapped[Optional["DjangoContentType"]] = relationship(
        "DjangoContentType", back_populates="django_admin_log"
    )
    user: Mapped["ApiUser"] = relationship("ApiUser", back_populates="django_admin_log")


class EssaysEssay(Base):
    __tablename__ = "essays_essay"
    __table_args__ = (
        ForeignKeyConstraint(
            ["author_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="essays_essay_author_id_681c67f4_fk_api_user_id",
        ),
        ForeignKeyConstraint(
            ["essay_topic_id"],
            ["essays_essaytopic.id"],
            deferrable=True,
            initially="DEFERRED",
            name="essays_essay_essay_topic_id_44c0f68e_fk_essays_essaytopic_id",
        ),
        ForeignKeyConstraint(
            ["essay_type_id"],
            ["essays_essaytype.name"],
            deferrable=True,
            initially="DEFERRED",
            name="essays_essay_essay_type_id_2a86fca3_fk_essays_essaytype_name",
        ),
        PrimaryKeyConstraint("id", name="essays_essay_pkey"),
        UniqueConstraint(
            "author_id", "essay_topic_id", name="unique_essay_per_user_per_topic"
        ),
        Index("essays_essay_author_id_681c67f4", "author_id"),
        Index("essays_essay_essay_topic_id_44c0f68e", "essay_topic_id"),
        Index("essays_essay_essay_type_id_2a86fca3", "essay_type_id"),
        Index("essays_essay_essay_type_id_2a86fca3_like", "essay_type_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    original_file: Mapped[str] = mapped_column(String(100))
    cleaned_text: Mapped[str] = mapped_column(Text)
    user_corrected_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    essay_topic_id: Mapped[int] = mapped_column(BigInteger)
    author_id: Mapped[int] = mapped_column(Integer)
    essay_type_id: Mapped[str] = mapped_column(String(255))

    author: Mapped["ApiUser"] = relationship("ApiUser", back_populates="essays_essay")
    essay_topic: Mapped["EssaysEssaytopic"] = relationship(
        "EssaysEssaytopic", back_populates="essays_essay"
    )
    essay_type: Mapped["EssaysEssaytype"] = relationship(
        "EssaysEssaytype", back_populates="essays_essay"
    )
    essays_extractedtext: Mapped[List["EssaysExtractedtext"]] = relationship(
        "EssaysExtractedtext", back_populates="essay"
    )
    essays_feedback: Mapped[List["EssaysFeedback"]] = relationship(
        "EssaysFeedback", back_populates="essay"
    )


class FcmDjangoFcmdevice(Base):
    __tablename__ = "fcm_django_fcmdevice"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="fcm_django_fcmdevice_user_id_6cdfc0a2_fk_api_user_id",
        ),
        PrimaryKeyConstraint("id", name="fcm_django_fcmdevice_pkey"),
        UniqueConstraint(
            "registration_id", name="fcm_django_fcmdevice_registration_id_9918b353_uniq"
        ),
        Index("fcm_django__registr_dacdb2_idx", "registration_id", "user_id"),
        Index("fcm_django_fcmdevice_device_id_a9406c36", "device_id"),
        Index("fcm_django_fcmdevice_registration_id_9918b353_like", "registration_id"),
        Index("fcm_django_fcmdevice_user_id_6cdfc0a2", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    active: Mapped[bool] = mapped_column(Boolean)
    registration_id: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(10))
    name: Mapped[Optional[str]] = mapped_column(String(255))
    date_created: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    device_id: Mapped[Optional[str]] = mapped_column(String(255))
    user_id: Mapped[Optional[int]] = mapped_column(Integer)

    user: Mapped[Optional["ApiUser"]] = relationship(
        "ApiUser", back_populates="fcm_django_fcmdevice"
    )


class QuizSessionparticipation(Base):
    __tablename__ = "quiz_sessionparticipation"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id"],
            ["quiz_session.id"],
            deferrable=True,
            initially="DEFERRED",
            name="quiz_sessionparticipant_session_id_aa4ef14f_fk_quiz_session_id",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="quiz_sessionparticipant_user_id_fa02620a_fk_api_user_id",
        ),
        PrimaryKeyConstraint("id", name="quiz_sessionparticipant_pkey"),
        UniqueConstraint(
            "session_id", "user_id", name="unique_session_user_participant"
        ),
        Index("quiz_sessionparticipant_session_id_aa4ef14f", "session_id"),
        Index("quiz_sessionparticipant_user_id_fa02620a", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    confirmed: Mapped[bool] = mapped_column(Boolean)
    session_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(Integer)
    duel_score_change: Mapped[Optional[float]] = mapped_column(Double(53))

    session: Mapped["QuizSession"] = relationship(
        "QuizSession", back_populates="quiz_sessionparticipation"
    )
    user: Mapped["ApiUser"] = relationship(
        "ApiUser", back_populates="quiz_sessionparticipation"
    )


class QuizSessionquestionuser(Base):
    __tablename__ = "quiz_sessionquestionuser"
    __table_args__ = (
        CheckConstraint(
            "choice_id IS NOT NULL AND submitted_text = ''::text AND NOT timed_out OR choice_id IS NULL AND NOT submitted_text = ''::text AND NOT timed_out OR choice_id IS NULL AND submitted_text = ''::text",
            name="session_question_user_valid_states",
        ),
        ForeignKeyConstraint(
            ["choice_id"],
            ["quiz_choice.id"],
            deferrable=True,
            initially="DEFERRED",
            name="quiz_sessionquestionanswer_choice_id_165d4802_fk_quiz_choice_id",
        ),
        ForeignKeyConstraint(
            ["session_question_id"],
            ["quiz_sessionquestion.id"],
            deferrable=True,
            initially="DEFERRED",
            name="quiz_sessionquestion_session_question_id_4ce75b91_fk_quiz_sess",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="quiz_sessionquestionanswer_user_id_56fb2ee5_fk_api_user_id",
        ),
        PrimaryKeyConstraint("id", name="quiz_sessionquestionanswer_pkey"),
        UniqueConstraint(
            "session_question_id", "user_id", name="unique_session_question_user_answer"
        ),
        Index("quiz_sessionquestionanswer_choice_id_165d4802", "choice_id"),
        Index(
            "quiz_sessionquestionanswer_session_question_id_4ce75b91",
            "session_question_id",
        ),
        Index("quiz_sessionquestionanswer_user_id_56fb2ee5", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    submitted_text: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    feedback: Mapped[str] = mapped_column(Text)
    session_question_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(Integer)
    timed_out: Mapped[bool] = mapped_column(Boolean)
    grade: Mapped[Optional[float]] = mapped_column(Double(53))
    choice_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    choice: Mapped[Optional["QuizChoice"]] = relationship(
        "QuizChoice", back_populates="quiz_sessionquestionuser"
    )
    session_question: Mapped["QuizSessionquestion"] = relationship(
        "QuizSessionquestion", back_populates="quiz_sessionquestionuser"
    )
    user: Mapped["ApiUser"] = relationship(
        "ApiUser", back_populates="quiz_sessionquestionuser"
    )


class QuizUserinfo(Base):
    __tablename__ = "quiz_userinfo"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="quiz_userinfo_user_id_e27b13c7_fk_api_user_id",
        ),
        PrimaryKeyConstraint("id", name="quiz_userinfo_pkey"),
        UniqueConstraint("user_id", name="quiz_userinfo_user_id_key"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(Integer)
    dynamic_score: Mapped[float] = mapped_column(Double(53))
    humanities_score: Mapped[Optional[float]] = mapped_column(Double(53))
    language_score: Mapped[Optional[float]] = mapped_column(Double(53))
    math_score: Mapped[Optional[float]] = mapped_column(Double(53))
    science_score: Mapped[Optional[float]] = mapped_column(Double(53))
    average_score: Mapped[Optional[float]] = mapped_column(
        Double(53),
        Computed(
            "((((math_score + language_score) + humanities_score) + science_score) / (4)::double precision)",
            persisted=True,
        ),
    )
    duel_score: Mapped[Optional[float]] = mapped_column(Double(53))

    user: Mapped["ApiUser"] = relationship("ApiUser", back_populates="quiz_userinfo")


class StudyPlansStudyplan(Base):
    __tablename__ = "study_plans_studyplan"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["api_user.id"],
            deferrable=True,
            initially="DEFERRED",
            name="study_plans_studyplan_user_id_6464a38d_fk_api_user_id",
        ),
        PrimaryKeyConstraint("id", name="study_plans_studyplan_pkey"),
        Index("study_plans_studyplan_user_id_6464a38d", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1
        ),
        primary_key=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    user_id: Mapped[int] = mapped_column(Integer)
    calendar: Mapped[Optional[dict]] = mapped_column(JSONB)

    user: Mapped["ApiUser"] = relationship(
        "ApiUser", back_populates="study_plans_studyplan"
    )


class ApiEmbeddedfileMessages(Base):
    __tablename__ = "api_embeddedfile_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["embeddedfile_id"],
            ["api_embeddedfile.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_embeddedfile_mes_embeddedfile_id_2f4b0914_fk_api_embed",
        ),
        ForeignKeyConstraint(
            ["message_id"],
            ["api_message.id"],
            deferrable=True,
            initially="DEFERRED",
            name="api_embeddedfile_messages_message_id_615df831_fk_api_message_id",
        ),
        PrimaryKeyConstraint("id", name="api_embeddedfile_messages_pkey"),
        UniqueConstraint(
            "embeddedfile_id",
            "message_id",
            name="api_embeddedfile_message_embeddedfile_id_message__9b49fa22_uniq",
        ),
        Index("api_embeddedfile_messages_embeddedfile_id_2f4b0914", "embeddedfile_id"),
        Index("api_embeddedfile_messages_message_id_615df831", "message_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    embeddedfile_id: Mapped[int] = mapped_column(Integer)
    message_id: Mapped[int] = mapped_column(Integer)

    embeddedfile: Mapped["ApiEmbeddedfile"] = relationship(
        "ApiEmbeddedfile", back_populates="api_embeddedfile_messages"
    )
    message: Mapped["ApiMessage"] = relationship(
        "ApiMessage", back_populates="api_embeddedfile_messages"
    )


class EssaysExtractedtext(Base):
    __tablename__ = "essays_extractedtext"
    __table_args__ = (
        ForeignKeyConstraint(
            ["essay_id"],
            ["essays_essay.id"],
            deferrable=True,
            initially="DEFERRED",
            name="essays_extractedtext_essay_id_a5cf37e6_fk_essays_essay_id",
        ),
        PrimaryKeyConstraint("id", name="essays_extractedtext_pkey"),
        Index("essays_extractedtext_essay_id_a5cf37e6", "essay_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    extraction_method: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    essay_id: Mapped[int] = mapped_column(BigInteger)

    essay: Mapped["EssaysEssay"] = relationship(
        "EssaysEssay", back_populates="essays_extractedtext"
    )


class EssaysFeedback(Base):
    __tablename__ = "essays_feedback"
    __table_args__ = (
        ForeignKeyConstraint(
            ["essay_id"],
            ["essays_essay.id"],
            deferrable=True,
            initially="DEFERRED",
            name="essays_feedback_essay_id_9555daab_fk_essays_essay_id",
        ),
        ForeignKeyConstraint(
            ["feedback_category_id"],
            ["essays_feedbackcategory.id"],
            deferrable=True,
            initially="DEFERRED",
            name="essays_feedback_feedback_category_id_da6f6aca_fk_essays_fe",
        ),
        PrimaryKeyConstraint("id", name="essays_feedback_pkey"),
        Index("essays_feedback_essay_id_9555daab", "essay_id"),
        Index("essays_feedback_feedback_category_id_da6f6aca", "feedback_category_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
    )
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True))
    feedback_category_id: Mapped[int] = mapped_column(BigInteger)
    essay_id: Mapped[int] = mapped_column(BigInteger)
    grade: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 2))

    essay: Mapped["EssaysEssay"] = relationship(
        "EssaysEssay", back_populates="essays_feedback"
    )
    feedback_category: Mapped["EssaysFeedbackcategory"] = relationship(
        "EssaysFeedbackcategory", back_populates="essays_feedback"
    )
