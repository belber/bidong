from datetime import datetime

from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, Table, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .time import utcnow_naive


card_tag = Table(
    "card_tag",
    Base.metadata,
    Column("card_id", ForeignKey("video_card.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    openid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    nickname: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)


class VideoCard(Base):
    __tablename__ = "video_card"
    __table_args__ = (UniqueConstraint("user_id", "bvid", name="uq_video_card_user_bvid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    bvid: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(Text)
    cover_url: Mapped[str] = mapped_column(Text)
    up_name: Mapped[str] = mapped_column(String(128))
    partition: Mapped[str] = mapped_column(String(64), default="")
    desc: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text)
    duration: Mapped[int] = mapped_column(Integer, default=0)
    pubdate: Mapped[int] = mapped_column(Integer, default=0)
    cid: Mapped[int] = mapped_column(BigInteger, default=0, server_default=text("0"))
    source: Mapped[str] = mapped_column(String(16), default="local")
    collected_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    month: Mapped[str] = mapped_column(String(7), index=True)

    tags: Mapped[list["Tag"]] = relationship(
        secondary=card_tag,
        back_populates="cards",
        lazy="selectin",
    )


class Tag(Base):
    __tablename__ = "tag"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_tag_user_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))

    cards: Mapped[list["VideoCard"]] = relationship(
        secondary=card_tag,
        back_populates="tags",
        lazy="selectin",
    )


class Binding(Base):
    __tablename__ = "binding"
    __table_args__ = (
        UniqueConstraint("bili_uid", name="uq_binding_bili_uid"),
        UniqueConstraint("activation_code", name="uq_binding_activation_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"), unique=True, nullable=True
    )
    bili_uid: Mapped[str] = mapped_column(String(32))
    bili_name: Mapped[str] = mapped_column(String(128), default="")
    activation_code: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    code_sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_follow_mtime: Mapped[int] = mapped_column(Integer, default=0)
    bound_at: Mapped[datetime | None] = mapped_column(nullable=True)


class RobotCursor(Base):
    __tablename__ = "robot_cursor"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), unique=True)
    last_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_time: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow_naive, onupdate=utcnow_naive
    )


class FollowEvent(Base):
    """每次「发现新关注」落一条，按 (bili_uid, mtime) 去重。"""

    __tablename__ = "follow_event"
    __table_args__ = (
        UniqueConstraint("bili_uid", "mtime", name="uq_follow_event_uid_mtime"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bili_uid: Mapped[str] = mapped_column(String(32), index=True)
    bili_name: Mapped[str] = mapped_column(String(128), default="")
    mtime: Mapped[int] = mapped_column(Integer, default=0)
    sent_code: Mapped[bool] = mapped_column(default=False)
    bound: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)


class AtEvent(Base):
    """评论区 @ 通知，按 feed id 去重。"""

    __tablename__ = "at_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    feed_id: Mapped[str] = mapped_column(String(64), unique=True)
    bili_uid: Mapped[str] = mapped_column(String(32), index=True)
    bili_name: Mapped[str] = mapped_column(String(128), default="")
    bvid: Mapped[str] = mapped_column(String(32), default="")
    video_title: Mapped[str] = mapped_column(String(256), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(String(32), default="collected")
    reason: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)


class ActivationLog(Base):
    """每次「发码尝试」落一条。"""

    __tablename__ = "activation_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    bili_uid: Mapped[str] = mapped_column(String(32), index=True)
    bili_name: Mapped[str] = mapped_column(String(128), default="")
    code: Mapped[str] = mapped_column(String(32), default="")
    sent_ok: Mapped[bool] = mapped_column(default=False)
    send_reason: Mapped[str] = mapped_column(String(64), default="")
    bound: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)


class ParseLog(Base):
    """每次「解析尝试」落一条。"""

    __tablename__ = "parse_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(16), index=True)  # local | robot
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"), nullable=True, index=True
    )
    bili_uid: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    input: Mapped[str] = mapped_column(Text, default="")
    bvid: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    video_title: Mapped[str] = mapped_column(String(256), default="")
    ok: Mapped[bool] = mapped_column(default=False)
    reason: Mapped[str] = mapped_column(String(64), default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)


class AdminConfig(Base):
    """动态配置的 key-value 存储，读时优先 DB，缺省回退 env。"""

    __tablename__ = "admin_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow_naive, onupdate=utcnow_naive
    )
