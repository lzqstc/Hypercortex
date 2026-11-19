from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    template: str = Field(default="产品知识库", max_length=120)
    team: str = Field(default="产品与体验中心", max_length=120)
    visibility: str = Field(default="团队可见", max_length=120)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    question: str = Field(min_length=1, max_length=4000)
    project_id: str = Field(default="default", alias="projectId")
    top_k: int = Field(default=6, alias="topK", ge=1, le=20)
    include_citations: bool = Field(default=True, alias="citations")
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


class UrlIngestRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    url: str = Field(min_length=8, max_length=2048)
    project_id: str = Field(default="default", alias="projectId")


class CloudSyncRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    provider: str = Field(default="cloud", max_length=120)
    project_id: str = Field(default="default", alias="projectId")


class SettingsPatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    auto_sync: bool | None = Field(default=None, alias="autoSync")
    deep_search: bool | None = Field(default=None, alias="deepSearch")
    citations: bool | None = Field(default=None, alias="citations")

    def as_updates(self) -> dict[str, bool]:
        updates: dict[str, bool] = {}
        for key, value in (
            ("autoSync", self.auto_sync),
            ("deepSearch", self.deep_search),
            ("citations", self.citations),
        ):
            if value is not None:
                updates[key] = value
        return updates


class ResearchCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    topic: str = Field(min_length=1, max_length=2000)
    project_id: str = Field(default="default", alias="projectId")


class ResearchRun(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    topic: str | None = Field(default=None, min_length=1, max_length=2000)
