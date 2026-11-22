"""AskDocs API package: retrieval over section-anchored statute chunks."""

__all__ = ["create_app"]


def create_app():
    from askdocs_api.main import create_app as _create_app

    return _create_app()
