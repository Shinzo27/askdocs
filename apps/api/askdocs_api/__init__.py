"""AskDocs API package: retrieval over section-anchored statute chunks."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = ["create_app"]


def create_app() -> FastAPI:
    from askdocs_api.main import create_app as _create_app

    return _create_app()
