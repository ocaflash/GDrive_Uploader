# Dockerfile

FROM python:3.10-slim

WORKDIR /app

# Install Poetry
RUN pip install --no-cache-dir poetry

# Copy the pyproject.toml and poetry.lock files
COPY pyproject.toml poetry.lock* ./

# Install dependencies
RUN poetry install --no-dev --no-root

# Copy the rest of your application code
COPY . .

# Command to run your bot
CMD ["poetry", "run", "python", "bot.py"]
