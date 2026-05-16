FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system airp && adduser --system --ingroup airp airp

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip && pip install .

USER airp

EXPOSE 8080

CMD ["uvicorn", "airp.main:app", "--host", "0.0.0.0", "--port", "8080"]

