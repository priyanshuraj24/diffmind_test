import hashlib
from dataclasses import asdict, dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


@dataclass
class Chunk:
    path: str
    start: int
    end: int
    symbol: str
    text: str
    language: str

    @property
    def search_text(self):
        return f"{self.path}\n{self.language} {self.symbol}\n{self.text}"

    @property
    def content_id(self):
        return hashlib.sha256(self.search_text.encode()).hexdigest()

    def payload(self):
        return asdict(self) | {"content_id": self.content_id}


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(max_length=160)
    body: str = Field(max_length=3000)
    category: Literal["correctness", "security", "performance", "reliability"]
    severity: Literal["high", "medium"]
    path: str
    line: int = Field(gt=0)
    side: Literal["RIGHT", "LEFT"] = "RIGHT"
    evidence_ids: list[str] = Field(min_length=1, max_length=12)
    scenario: str = Field(min_length=10, max_length=1500)
    suggestion: str | None = Field(default=None, max_length=3000)


class ReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(max_length=4000)
    findings: list[Finding] = Field(max_length=20)
