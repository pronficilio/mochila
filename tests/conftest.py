import os


os.environ["APP_PASSWORD"] = "test-mochi"
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DATA_DIR", "/tmp/mochila-test-data")
