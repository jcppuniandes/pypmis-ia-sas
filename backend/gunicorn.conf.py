import os


bind = "0.0.0.0:8000"
worker_class = "uvicorn.workers.UvicornWorker"
workers = int(os.getenv("GUNICORN_WORKERS", "4"))
timeout = int(os.getenv("GUNICORN_TIMEOUT_SECONDS", "180"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT_SECONDS", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE_SECONDS", "5"))
accesslog = "-"
errorlog = "-"
