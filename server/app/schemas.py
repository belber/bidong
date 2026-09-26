from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    code: str


class UserOut(BaseModel):
    id: int
    nickname: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ParseRequest(BaseModel):
    url: str


class TagCreate(BaseModel):
    name: str


class CardTagsRequest(BaseModel):
    tags: list[str] = Field(default_factory=list)


class VideoStats(BaseModel):
    like: int = 0
    reply: int = 0
    favorite: int = 0
    coin: int = 0


class MediaAvailability(BaseModel):
    watermarked: bool = False
    clean: bool = False
    audio: bool = False


class ParseFeatures(BaseModel):
    comment: bool = True
    danmaku: bool = True


class MediaOption(BaseModel):
    qn: int
    label: str


class MediaDownloadCandidate(BaseModel):
    url: str
    host: str
    configured: bool


class MediaDownloadUrlResponse(BaseModel):
    kind: str
    qn: int | None = None
    expires_at: int | None = None
    candidates: list[MediaDownloadCandidate] = Field(default_factory=list)


class DownloadEventReport(BaseModel):
    card_id: int | None = None
    bvid: str = ""
    kind: str = ""
    qn: int | None = None
    host: str = ""
    candidate_index: int = 0
    stage: str = "download"
    status: str = "success"
    error_type: str = ""
    error_message: str = ""
    http_status: int | None = None
    wx_err_msg: str = ""


class VisitEventRequest(BaseModel):
    path: str = ""


class CardOut(BaseModel):
    id: int
    bvid: str
    title: str
    up_name: str
    partition: str
    duration: int
    pubdate: int
    cover_url: str
    desc: str
    source_url: str
    source: str
    tags: list[str]
    collected_at: int
    month: str


class SubtitleLine(BaseModel):
    t: int
    text: str


class OriginOut(BaseModel):
    """解析结果页的「帅哥录屏 · 原up主是谁」区块数据。

    出现即代表这条视频属于白名单账号；字段为空表示还在整理。
    """

    account_name: str = ""
    account_avatar_url: str = ""
    platform: str = ""
    platform_label: str = ""
    author_name: str = ""
    author_handle: str = ""
    author_url: str = ""


class ParseResult(CardOut):
    subtitles: list[SubtitleLine] = Field(default_factory=list)
    stats: VideoStats = Field(default_factory=VideoStats)
    danmaku_count: int = 0
    media: MediaAvailability = Field(default_factory=MediaAvailability)
    features: ParseFeatures = Field(default_factory=ParseFeatures)
    origin: OriginOut | None = None


class PublicCardOut(BaseModel):
    """免登录可见的视频信息：只有公开元数据，不含任何用户数据。"""

    bvid: str
    title: str
    up_name: str
    partition: str = ""
    duration: int = 0
    pubdate: int = 0
    cover_url: str = ""
    desc: str = ""
    source_url: str = ""
    origin: OriginOut | None = None


class BindingRequest(BaseModel):
    code: str


class BindingOut(BaseModel):
    bound: bool
    bili_uid: str | None = None
    bili_name: str | None = None
