"""
database/init_db.py
---------------------
Creates every table registered on db.metadata. Safe to run repeatedly --
SQLAlchemy's create_all() only creates tables that don't already exist, it
never drops or overwrites data. To fully reset during development, delete
the "flood_nowcasting.db" file and re-run this.

Usage:
    flask --app app init-db
or, standalone:
    python -m database.init_db
"""

from flask import Flask
from extensions import db
import models  # noqa: F401 -- import registers every model with db.metadata


def init_db(app: Flask) -> None:
    with app.app_context():
        db.create_all()
        # Create the judge/demo admin account if it does not exist.
        from models import User
        email = app.config["ADMIN_EMAIL"]
        if User.query.filter_by(email=email).first() is None:
            admin = User(
                username=app.config["ADMIN_USERNAME"],
                email=email,
                role="admin",
            )
            admin.set_password(app.config["ADMIN_PASSWORD"])
            db.session.add(admin)
            db.session.commit()
            print(f"Created admin account: {email}")


if __name__ == "__main__":
    from app import create_app
    application = create_app()
    init_db(application)
    print("Database tables created.")
