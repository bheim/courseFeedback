"""Public, backward-compatible course-feedback API."""


def create_app(*args, **kwargs):
    """Import the Flask application lazily so release checks remain standalone."""

    from .app import create_app as app_factory

    return app_factory(*args, **kwargs)


__all__ = ["create_app"]
