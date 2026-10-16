FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install ffmpeg (used by grandpa effect) and clean up apt caches
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy the full project first so any referenced requirements files are present
COPY . .

# Install Python dependencies (root requirements can reference tts-bot/requirements.txt)
RUN pip install --no-cache-dir -r requirements.txt

# Start the bot
CMD ["python", "tts-bot/bot.py"]
