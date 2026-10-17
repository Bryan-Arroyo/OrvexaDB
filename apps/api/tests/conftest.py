import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/orvexadb_test")
os.environ.setdefault("AUTH_PEPPER", "unit-test-auth-pepper-0123456789-abcdef")
