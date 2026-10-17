FROM python:3.12.7-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
RUN useradd --create-home appuser
USER appuser
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
