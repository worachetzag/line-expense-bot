import os

# Tests must never touch the real Turso database.
# Overriding the env vars here (before app.config is imported) beats the .env file.
os.environ["TURSO_DATABASE_URL"] = ""
os.environ["TURSO_AUTH_TOKEN"] = ""
