FROM python:3.10-slim
WORKDIR /app
RUN pip install --no-cache-dir poetry
COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-root
COPY . .
CMD ["poetry", "run", "python", "bot.py"]
