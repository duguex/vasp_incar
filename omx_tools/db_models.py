"""Pydantic response/suggestion models for the OpenMX manual database.

These models are defined once here and imported by the ``omx-db`` CLI
(``omx_tools.database``). They shape the structured output of the query
commands and stay independent of search/DB plumbing.
"""

from __future__ import annotations

from pydantic import BaseModel


class SearchResult(BaseModel):
    sec_num: str | None = None
    title: str
    rank: float
    snippet: str = ""


class SearchResponse(BaseModel):
    results: list[SearchResult] = []
    count: int = 0
    query: str = ""
    _debug: list[str] | None = None


class HybridResult(BaseModel):
    sec_num: str | None = None
    title: str
    score: float
    source: str  # "fts5" | "semantic" | "hybrid"


class HybridResponse(BaseModel):
    results: list[HybridResult] = []
    count: int = 0
    query: str = ""
    _debug: list[str] | None = None


class KeywordEntry(BaseModel):
    keyword: str | None = None
    sec_num: str | None = None
    title: str | None = None


class SectionEntry(BaseModel):
    sec_num: str
    title: str
    depth: int = 1
    file: str | None = None
    content: str | None = None


class ErrorResponse(BaseModel):
    error: str
    suggestion: str = ""


class SectionSuggestions(BaseModel):
    error: str
    suggestion: str = ""
    suggestions: list[dict] = []