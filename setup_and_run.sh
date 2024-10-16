#!/bin/bash

# Установка virtualenv для изоляции окружения
python3.10 -m venv venv
source venv/bin/activate

# Обновление pip и установка Poetry
pip install --upgrade pip
pip install poetry

# Установка зависимостей через Poetry
poetry install --no-dev --no-root

# Запуск бота
poetry run python bot.py
