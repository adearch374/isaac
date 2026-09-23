"""Auto-loaded gunicorn configuration (gunicorn picks up ./gunicorn.conf.py
automatically, and Render runs `gunicorn app:app`, so these settings apply).

The bulk student upload hashes one password per student (scrypt, ~0.1-0.2s
each) plus several database round-trips per row. With gunicorn's default
30-second worker timeout, the master killed the worker in the middle of large
uploads: the browser got a generic "Internal Server Error" and the credentials
CSV was never generated, even though the rows committed before the kill stayed
in the database. 300s comfortably covers the 1000-row limit of a single upload.
"""
import os

timeout = int(os.environ.get('GUNICORN_TIMEOUT', '300'))
graceful_timeout = timeout

