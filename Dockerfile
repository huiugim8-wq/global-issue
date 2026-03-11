FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt

COPY backend ./backend
COPY frontend ./frontend
COPY main.py ./main.py
COPY .env.example ./.env.example

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
