FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml requirements.txt ./
COPY recallops ./recallops
RUN pip install --no-cache-dir .
RUN mkdir -p /app/data/raw /app/data/quarantine
EXPOSE 8000
CMD ["uvicorn", "recallops.api:app", "--host", "0.0.0.0", "--port", "8000"]
