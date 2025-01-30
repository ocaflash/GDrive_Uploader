# Telegram Google Drive Bot

This Telegram bot allows users to upload photos directly to selected folders on Google Drive.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Error Handling](#error-handling)
- [License](#license)

## Features

- Upload photos to Google Drive via Telegram
- Select destination folder using interactive buttons
- Automatic creation of date-based subfolders for organized uploads
- Upload statistics tracking
- Access restriction to specific users

## Requirements

- Python 3.9+
- telebot
- google-auth
- google-auth-oauthlib
- google-auth-httplib2
- google-api-python-client

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/ocaflash/GDrive_Uploader.git
   cd GDrive_Uploader
   ```

2. Install dependencies:
   ```
   pip install --upgrade pip
   pip install poetry
   poetry install --no-root
   ```

## Configuration

1. Create a project in the [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the Google Drive API for your project
3. Create service account credentials and download the JSON key
4. Rename the JSON key to `credentials.json` and place it in the project root folder
5. Create a bot on Telegram via [@BotFather](https://t.me/botfather) and obtain the API token
6. Copy `.env.example` to `.env` and fill in the required parameters:
   - `API_TOKEN`: your Telegram bot token
   - `ALLOWED_USERS`: list of Telegram user IDs allowed to use the bot
   - `GOOGLE_DRIVE_CREDENTIALS_FILE`: path to your `credentials.json` file
   - Other settings as desired

## Usage

1. Start the bot:
   ```
   poetry run python bot.py
   ```

2. In Telegram, start a conversation with the bot using the `/start` command
3. Send a photo to the bot
4. Choose the destination folder from the provided buttons
5. The bot will upload the photo to the selected folder on Google Drive

## Project Structure

- `bot.py`: main bot file
- `gdrive_service.py`: module for interacting with Google Drive API
- `config.py`: configuration file
- `pyproject.toml, poetry.lock`: list of project dependencies

## Error Handling

The bot includes error handling and retry mechanisms to ensure stable operation:

- Exponential backoff for connection retries
- Error logging for problem diagnosis
- Middleware for handling exceptions during request processing

Check the logs for additional information if issues occur.
