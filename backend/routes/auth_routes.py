"""Authentication endpoints for the SIH demo."""

from flask import Blueprint, jsonify, request
from models.user import User
from extensions import db


auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))

    if not email or not password:
        return jsonify({"data": None, "error": "Email and password are required."}), 400

    user = User.query.filter_by(email=email).first()
    if user is None or not user.check_password(password):
        return jsonify({"data": None, "error": "Invalid email or password."}), 401

    return jsonify({
        "data": {"user": user.to_dict()},
        "meta": {"authenticated": True},
    })


@auth_bp.get("/auth/me")
def me():
    email = request.headers.get("X-User-Email", "").strip().lower()
    user = User.query.filter_by(email=email).first() if email else None
    if user is None:
        return jsonify({"data": None, "error": "Not authenticated."}), 401
    return jsonify({"data": {"user": user.to_dict()}, "meta": {"authenticated": True}})
