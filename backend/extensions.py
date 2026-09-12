"""
extensions.py
-------------
Extension instances are created here, UNBOUND to any specific Flask app, and
then attached to the app inside app.py's create_app(). This is the standard
"application factory" pattern — it avoids circular imports between app.py,
models/*.py, and routes/*.py, because every one of those files can safely
`from extensions import db` without needing app.py to exist yet.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

db = SQLAlchemy()
cors = CORS()
