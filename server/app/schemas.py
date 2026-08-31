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
