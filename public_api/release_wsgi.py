"""Fail-closed WSGI entrypoint for the deployed public extension API."""

from .app import create_release_app


app = create_release_app()
