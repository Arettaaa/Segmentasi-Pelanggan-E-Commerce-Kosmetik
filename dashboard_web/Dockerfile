FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8502
CMD ["gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:8502", "app:app"]
