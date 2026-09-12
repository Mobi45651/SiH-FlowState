"""
tests/conftest.py
-------------------
Provides a `client` fixture backed by an in-memory SQLite database (via
TestingConfig) so tests never touch the real flood_nowcasting.db file and
can run in any order without leftover state.
"""

import pytest
from app import create_app
from extensions import db


@pytest.fixture
def app():
    application = create_app("testing")
    with application.app_context():
        import models  # noqa: F401 -- registers tables
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
