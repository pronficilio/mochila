from typing import Literal
from pydantic import BaseModel, Field, field_validator
from .urls import validate_youtube_url


class LoginRequest(BaseModel):
    password: str = Field(min_length=1)


class CreateJobRequest(BaseModel):
    url: str
    mode: Literal["video", "audio"] = "video"
    max_height: int | None = Field(default=None, ge=144, le=4320)
    audio_format: Literal["m4a", "mp3"] = "m4a"

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return validate_youtube_url(value)


class JobResponse(BaseModel):
    id: str
    status: str
    mode: str
    url: str
    created_at: str
    updated_at: str
    error: str | None = None
    filename: str | None = None
    download_url: str | None = None
