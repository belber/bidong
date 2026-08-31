from datetime import datetime

from sqlalchemy import Column, ForeignKey, Integer, String, Table, Text, UniqueConstraint, text
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
    cid: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
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
