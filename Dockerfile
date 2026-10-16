# Dockerfile to run the Telegram TTS bot
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install ffmpeg (used by grandpa effect) and clean up apt caches
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Use the same start command as Procfile
CMD ["python", "tts-bot/bot.py"]
