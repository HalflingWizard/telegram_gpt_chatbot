# Telegram GPT Bot

## 1. Project overview

This project is a private Python Telegram bot that lets approved Telegram users talk to an OpenAI model from Telegram. It uses the OpenAI Responses API for conversation turns, stores chat history locally in SQLite, and supports text, images, and file uploads with per-user chat browsing through short custom chat IDs.

The bot is designed for maintainability rather than cleverness. The code is split into handlers, services, repositories, and database models so a future RA can inspect the state locally, add new commands, and migrate the storage layer later if needed.

## 2. Features

Implemented in this repository:

- `/start` welcome message
- `/help` command list
- `/newchat` creates a new active chat with a short public ID
- `/chat <id>` restores an existing chat and makes it active
- `/listchats` shows recent chats with title, chat ID, and updated time, plus inline buttons
- `/currentchat` shows the active chat
- `/deletechat <id>` soft deletes a chat
- `/preferences` opens a menu to view, add, edit, or delete per-user reply preferences
- Text messages routed to the active chat
- Image uploads with optional caption
- File uploads with optional caption
- OpenAI file uploads with `purpose="user_data"`
- Local chat titles generated after the first user turn
- Automatic sticker sent on `/start` and `/newchat`
- Optional old-chat history preview after loading a saved chat
- Whitelist-only access control
- Structured JSON logging
- Unit tests for auth, chat service, title service, and handler behavior

Deferred or partial:

- Telegram media albums are not fully aggregated in v1, but the media handler and attachment model are structured so album support can be added without rewriting the whole flow
- Webhook deployment is documented as an extension path; the current runtime uses long polling
- Database migrations are not added yet; v1 bootstraps SQLite schema with SQLAlchemy `create_all`

## 3. Tech stack

- Python: 3.11+
- Telegram library: `python-telegram-bot` 21.x
- OpenAI library: `openai` Python SDK with the Responses API
- Database: SQLite
- ORM: SQLAlchemy 2.x
- Migration tool: not included in v1; schema bootstrap currently uses SQLAlchemy metadata creation

## 4. Repository structure

```text
telegram_gpt_chatbot/
├── README.md
├── .env.example
├── requirements.txt
├── pyproject.toml
├── main.py
├── bot/
│   ├── __init__.py
│   ├── config.py
│   ├── logging_setup.py
│   ├── telegram_app.py
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py
│   │   ├── chat_commands.py
│   │   ├── text_messages.py
│   │   ├── media_messages.py
│   │   └── errors.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── chat_service.py
│   │   ├── openai_service.py
│   │   ├── title_service.py
│   │   ├── telegram_file_service.py
│   │   └── formatting_service.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── session.py
│   │   └── repositories.py
│   └── utils/
│       ├── __init__.py
│       ├── ids.py
│       ├── time.py
│       └── validators.py
├── tests/
│   ├── test_auth.py
│   ├── test_chat_service.py
│   ├── test_title_service.py
│   └── test_handlers.py
└── data/
    └── .gitkeep
```

What each major area owns:

- `bot/handlers`: Telegram update entrypoints and user-visible behavior
- `bot/services`: Application logic and external API integration
- `bot/db`: SQLAlchemy schema and repositories
- `bot/utils`: small shared helpers
- `tests`: focused unit tests for core behavior
- `data`: default location for the SQLite database file

## 5. Local setup

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create the environment file:

```bash
cp .env.example .env
```

Edit `.env` and fill in the required secrets and user IDs.

Start the bot:

```bash
python main.py
```

Run tests:

```bash
pytest
```

## 6. Environment variables

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from BotFather |
| `OPENAI_API_KEY` | Yes | OpenAI API key for Responses and Files API calls |
| `ALLOWED_TELEGRAM_USER_IDS` | Yes | Comma-separated whitelist of Telegram numeric user IDs |
| `OPENAI_MAIN_MODEL` | Yes | Main assistant model name; defaults to `gpt-5.1` in `.env.example` |
| `OPENAI_TITLE_MODEL` | Yes | Lower-cost model for title generation; defaults to `gpt-5-mini` |
| `OPENAI_REASONING_EFFORT` | Yes | Reasoning budget for the main assistant; defaults to `medium` |
| `DATABASE_URL` | Yes | SQLAlchemy database URL; default is `sqlite:///data/telegram_gpt_bot.db` |
| `LOG_LEVEL` | Yes | Logging level such as `INFO` or `DEBUG` |
| `OPENAI_TIMEOUT_SECONDS` | No | Timeout for OpenAI requests |
| `TELEGRAM_FILE_SIZE_LIMIT_MB` | No | Max file size accepted by this bot before Telegram download rejection |
| `DEFAULT_STICKER_FILE_ID` | No | Telegram sticker file ID sent automatically on `/start` and `/newchat` |

## 7. Telegram setup

1. Open Telegram and message `@BotFather`.
2. Run `/newbot` and follow the prompts.
3. Copy the bot token and place it in `TELEGRAM_BOT_TOKEN`.
4. Start a direct chat with your new bot so Telegram can deliver updates to it.
5. Find your Telegram user ID and place it in `ALLOWED_TELEGRAM_USER_IDS`.

Ways to get your Telegram user ID:

- Use a small helper bot that reports your user ID
- Temporarily log `update.effective_user.id` in a local test bot session
- Use Telegram’s API tooling if you already have it in your environment

Runtime mode:

- This repository currently runs with long polling through `application.run_polling()`
- If you later want webhooks, keep the handler layer as-is and swap the bootstrap layer in `bot/telegram_app.py`

Telegram references:

- Bot platform overview: [Telegram Bot Platform](https://core.telegram.org/bots)
- Bot API reference: [Telegram Bot API](https://core.telegram.org/bots/api)

## 8. OpenAI setup

1. Create an API key in your OpenAI account.
2. Put the key in `OPENAI_API_KEY`.
3. Set the model names in `.env`.
4. Start the bot and send a message in Telegram.

Why this project uses the Responses API:

- OpenAI recommends Responses for reasoning models and newer state handling patterns
- The SDK exposes `response.output_text`, which lets the bot return only the final assistant answer to Telegram
- The same API shape supports text, image, and file input

How file uploads work:

- Telegram media is downloaded locally first
- The local file is uploaded to OpenAI with `purpose="user_data"`
- The returned OpenAI file ID is attached to the Responses request

Reasoning settings:

- The main assistant uses `OPENAI_REASONING_EFFORT`, default `medium`
- Title generation uses a smaller model to reduce cost and latency

Important note about model names:

- The original project brief asked for `gpt-5.4`
- On April 17, 2026, the public OpenAI docs I checked still documented the Responses API and GPT-5 reasoning models, but the public model references I found listed `gpt-5.1` and `gpt-5`, not `gpt-5.4`
- For that reason, this repository keeps the model fully configurable and uses `gpt-5.1` in `.env.example`
- If `gpt-5.4` is available in your account or your organization’s docs, set `OPENAI_MAIN_MODEL=gpt-5.4`

OpenAI references:

- Responses API guide: [OpenAI Responses API](https://platform.openai.com/docs/guides/responses)
- File inputs guide: [OpenAI File Inputs](https://platform.openai.com/docs/guides/pdf-files)
- Model overview: [OpenAI Models](https://platform.openai.com/docs/models)

## 9. How chats are stored

The SQLite database has five main tables.

`users`

- One row per Telegram user known to the bot
- Stores Telegram ID, username, allow/deny status, and saved user preferences

`chats`

- One row per user-visible conversation
- Stores the short public chat ID, title, active flag, timestamps, and soft-delete state

`messages`

- One row per stored user or assistant message
- Stores message role, text, Telegram message ID, and the OpenAI response ID when present

`message_attachments`

- One row per file or image attachment
- Stores both Telegram file metadata and the matching OpenAI file ID

`chat_state`

- One row per chat for mutable state
- Stores the last OpenAI response ID used for chained conversation continuity

Why local storage is still used even with OpenAI conversation chaining:

- The bot needs short custom chat IDs
- The bot needs local chat browsing and recovery
- Local data makes debugging and future migration easier
- The next RA can inspect the SQLite file without depending on a remote console

## 10. How to add a new command

1. Add a new handler function under `bot/handlers/`.
2. Give the handler a short module comment block and docstrings for public functions.
3. Put business logic in a service under `bot/services/` if the handler would otherwise become stateful or complex.
4. Register the command in `build_application()` in [bot/telegram_app.py](/Users/mn864/Documents/git/telegram_gpt_chatbot/bot/telegram_app.py).
5. Add or update tests under `tests/`.
6. Document the command in this README and in the help text in [bot/services/formatting_service.py](/Users/mn864/Documents/git/telegram_gpt_chatbot/bot/services/formatting_service.py).

## 11. How to rotate keys

Telegram token rotation:

1. Open `@BotFather`
2. Regenerate the bot token
3. Update `TELEGRAM_BOT_TOKEN` in your deployment environment
4. Restart the bot
5. Confirm the old token no longer works

OpenAI key rotation:

1. Create a new OpenAI API key
2. Update `OPENAI_API_KEY` in your local or deployed environment
3. Restart the bot
4. Revoke the old key after the new one is confirmed working

General rule:

- Never store secrets in git
- Keep secrets in `.env` locally and in your deployment secret manager in production

## 12. Troubleshooting

Bot not responding:

- Confirm the bot process is running
- Confirm `TELEGRAM_BOT_TOKEN` is valid
- Confirm you started a chat with the bot in Telegram
- Check logs for polling failures

Unauthorized user:

- Confirm the numeric Telegram user ID is in `ALLOWED_TELEGRAM_USER_IDS`
- Restart the bot after changing environment variables

File too large:

- Telegram bot downloads are intentionally capped in this app
- Reduce the file size or raise `TELEGRAM_FILE_SIZE_LIMIT_MB` only if your infrastructure supports it safely

OpenAI 401:

- `OPENAI_API_KEY` is missing, expired, revoked, or malformed

OpenAI 429:

- You hit rate or quota limits
- Retry later or adjust account limits and model selection

Missing dependencies:

- Recreate the virtual environment
- Run `pip install -r requirements.txt`

SQLite lock issues:

- Stop multiple bot processes that point to the same SQLite file
- Keep SQLite for single-user or small-whitelist usage
- If write contention becomes common, plan a migration to PostgreSQL

Corrupt chat state:

- The bot will ask the user to start a new chat if a chat cannot be restored safely
- Inspect `chat_state.last_openai_response_id` and recent logs

## 13. Maintenance guide

Routine maintenance:

- Back up `data/telegram_gpt_bot.db`
- Review logs for repeated upload or API failures
- Keep `requirements.txt` and `pyproject.toml` aligned
- Run tests after dependency upgrades
- Recheck OpenAI model availability before changing defaults

Recommended backup approach for SQLite:

```bash
cp data/telegram_gpt_bot.db data/telegram_gpt_bot.db.bak
```

When to migrate to PostgreSQL:

- Multiple concurrent bot workers
- Frequent locking
- More complex analytics or admin tooling
- Need for stronger operational guarantees

Migration path:

- Keep repository APIs stable
- Replace the database URL
- Add Alembic migrations
- Move from local file backups to managed database backups

## 14. Security notes

- This bot is private by design
- Always keep `ALLOWED_TELEGRAM_USER_IDS` configured
- Never run the bot with open access unless you intentionally redesign it
- Keep `TELEGRAM_BOT_TOKEN` and `OPENAI_API_KEY` out of source control
- Avoid logging full user content or file bodies

## Suggested implementation order for future work

1. Create the repo skeleton.
2. Add configuration loading and `.env.example`.
3. Set up SQLite models and repositories.
4. Implement Telegram app bootstrapping.
5. Implement the whitelist check.
6. Implement `/start`, `/help`, `/newchat`, and `/currentchat`.
7. Implement text chat flow with OpenAI.
8. Implement `/chat <id>` and `/listchats`.
9. Implement title generation after the first user message.
10. Implement image input flow.
11. Implement file upload flow.
12. Extend preference handling or richer sticker behavior if needed.
13. Add or expand tests.
14. Keep the README current.
15. Add a webhook deployment path if your hosting environment prefers it.

## Deployment notes

Local or single-machine deployment:

- Use the polling mode already implemented in `main.py`
- Keep the SQLite file on a persistent disk
- Run the bot under a process supervisor such as `systemd`, `supervisord`, or a container restart policy

If you later deploy behind webhooks:

- Replace polling bootstrap with a webhook listener in `bot/telegram_app.py`
- Put the service behind HTTPS
- Move SQLite to PostgreSQL if you need multiple instances
