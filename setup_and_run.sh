#!/bin/bash

# Установка virtualenv для изоляции окружения
python3.10 -m venv venv
source venv/bin/activate

# Обновление pip и установка Poetry
pip install --upgrade pip
pip install poetry
# for replit.com
# pip install --upgrade python-telegram-bot
# pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
# pip install python-dotenv



# Установка зависимостей через Poetry
poetry install --no-dev --no-root

# Запуск бота
poetry run python bot.py
