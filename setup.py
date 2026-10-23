from app import app
from db import init_db

with app.app_context():
    init_db()

print("FaceSecure database initialized successfully.")