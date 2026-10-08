FROM python:3.12-slim

WORKDIR /app
COPY server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY server/app /app/app
COPY knowledge-base /knowledge-base

ENV KNOWLEDGE_BASE_PATH=/knowledge-base
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

