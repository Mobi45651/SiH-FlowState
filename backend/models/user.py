"""
models/user.py
---------------
Minimal auth model. Not the focus of the SIH demo, but included so the
`role` field (citizen vs authority) can later gate which alerts/dashboards
a logged-in user sees. Passwords are always stored hashed, never plaintext.
"""

from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from models.base import TimestampMixin


class User(db.Model, TimestampMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # citizen / authority / admin — used to gate future authority-only views
    role = db.Column(db.String(20), nullable=False, default="citizen")

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
        }

    def __repr__(self):
        return f"<User {self.username}>"
