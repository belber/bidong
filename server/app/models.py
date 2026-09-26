from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
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
    up_mid: Mapped[str] = mapped_column(String(32), default="")
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


class BiliCdnDomain(Base):
    """B站 CDN 域名登记，用于微信 downloadFile 合法域名治理。"""

    __tablename__ = "bili_cdn_domain"

    id: Mapped[int] = mapped_column(primary_key=True)
    host: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    is_configured: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    seen_count: Mapped[int] = mapped_column(Integer, default=0)
    download_success_count: Mapped[int] = mapped_column(Integer, default=0)
    download_failure_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow_naive, onupdate=utcnow_naive
    )


class DownloadEvent(Base):
    """前端直连下载的关键阶段事件，用于下载监控与失败分析。"""

    __tablename__ = "download_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"), nullable=True, index=True
    )
    card_id: Mapped[int | None] = mapped_column(
        ForeignKey("video_card.id", ondelete="SET NULL"), nullable=True, index=True
    )
    bvid: Mapped[str] = mapped_column(String(32), default="", index=True)
    video_title: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(16), default="", index=True)
    qn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    host: Mapped[str] = mapped_column(String(255), default="", index=True)
    candidate_index: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    error_type: Mapped[str] = mapped_column(String(32), default="", index=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wx_err_msg: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)


class VisitEvent(Base):
    """小程序访问事件，用于统计每日活跃/访问用户。"""

    __tablename__ = "visit_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    path: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive, index=True)


class VideoSource(Base):
    """「帅哥录屏」稿件的出处。

    全局共用一张表，不按用户冗余——同一条视频的出处对所有用户都一样。
    由小主机（Hermes）上报，按 bvid 幂等 upsert。
    """

    __tablename__ = "video_source"

    id: Mapped[int] = mapped_column(primary_key=True)
    bvid: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    platform: Mapped[str] = mapped_column(String(32), default="")
    author_name: Mapped[str] = mapped_column(String(128), default="")
    author_handle: Mapped[str] = mapped_column(String(128), default="")
    author_id: Mapped[str] = mapped_column(String(128), default="")
    author_url: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    source_video_id: Mapped[str] = mapped_column(String(64), default="")
    bili_published_at: Mapped[str] = mapped_column(String(10), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow_naive, onupdate=utcnow_naive
    )


class CrawlerVisit(Base):
    """微信搜索爬虫的访问记录，用来回答"爬虫到底来没来过"。

    两个来源：服务端按请求头/UA 识别（source=header），以及小程序端按场景值
    1129 上报（source=scene）——爬虫打开页面时微信会带上这个场景值。
    """

    __tablename__ = "crawler_visit"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(16), default="header")  # header | scene
    path: Mapped[str] = mapped_column(String(255), default="")
    query: Mapped[str] = mapped_column(String(255), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    referer: Mapped[str] = mapped_column(String(255), default="")
    scene: Mapped[int] = mapped_column(Integer, default=0)
    # 签名校验结果：None = 没配 Token 无法校验
    signature_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive, index=True)
