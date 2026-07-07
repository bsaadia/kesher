import os

bind = f"0.0.0.0:{os.getenv('PORT', '10000')}"
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
# Dash callbacks can run non-trivial DB queries; the gunicorn default (30s)
# is too tight for that pattern.
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
