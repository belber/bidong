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


class ParseResult(CardOut):
    subtitles: list[SubtitleLine] = Field(default_factory=list)
    stats: VideoStats = Field(default_factory=VideoStats)
    danmaku_count: int = 0
    media: MediaAvailability = Field(default_factory=MediaAvailability)
    features: ParseFeatures = Field(default_factory=ParseFeatures)


class BindingRequest(BaseModel):
    code: str


class BindingOut(BaseModel):
    bound: bool
    bili_uid: str | None = None
    bili_name: str | None = None
