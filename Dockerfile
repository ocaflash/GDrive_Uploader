# Dockerfile

FROM python:3.10-slim

WORKDIR /app

# Install Poetry
RUN pip install --no-cache-dir poetry

# Copy the pyproject.toml and poetry.lock files
COPY pyproject.toml poetry.lock* ./

# Install dependencies (modern Poetry: use --only main instead of --no-dev)
RUN poetry install --only main --no-root

# Copy the rest of your application code
COPY . .

# Ensure downloads directory exists for userbot
RUN mkdir -p /app/downloads

# Command to run your userbot
CMD ["poetry", "run", "python", "userbot.py"]
