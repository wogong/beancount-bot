# Beancount Bot

A lightweight Telegram bot for adding transactions to your Beancount ledger file with fuzzy account matching.

## Features

- Add transactions via simple Telegram messages
- Fuzzy account name matching for fast entry
- Multi-leg transaction support
- Account completion based on usage frequency
- Transaction revert functionality
- Docker support with GitHub Container Registry

## Quick Start

### Using Docker (Recommended)

1. Create a bot with [@BotFather](https://t.me/BotFather) and get your bot token
2. Get your Telegram User ID from [@userinfobot](https://t.me/userinfobot)
3. Create a `.env` file with your configuration:
   ```bash
   BOT=your_bot_token_here
   CHAT_ID=your_telegram_user_id
   BEANCOUNT_ROOT=/data/main.beancount
   BEANCOUNT_OUTPUT=/data/transactions.beancount
   CURRENCY=CNY
   PROXY=  # Optional: leave empty if not needed
   ```
4. Run with Docker Compose:
   ```bash
   docker-compose up -d
   ```

### Using Python Directly

1. Create a bot with [@BotFather](https://t.me/BotFather) and get your bot token
2. Get your Telegram User ID from [@userinfobot](https://t.me/userinfobot)
3. Copy `src/.env.example` to `src/.env` and update with your values
4. Install dependencies and run:
   ```bash
   # Using uv (recommended)
   uv run src/bot.py

   # Or using pip
   python3 -m pip install -r requirements.txt
   python3 src/bot.py
   ```

### Docker Compose Configuration

The `docker-compose.yaml` uses the pre-built image from GitHub Container Registry by default:

```yaml
image: ghcr.io/wogong/beancount-bot:master
```

Update the volumes section with your beancount files path:
```yaml
volumes:
  - /path/to/your/beancount/files:/data
  - ./src/.env.docker:/app/src/.env
```

To build locally instead, uncomment the build section in `docker-compose.yaml`.

## Usage

### Adding Transactions

Send a message to the bot with the following format:

```
{account_from1 amount1} {account_from2 amount2} ... account_to note
```

**Rules:**
- Account names use fuzzy matching (similar to vim/vscode completion)
- First `2n+1` space-separated tokens are parsed as accounts and amounts
- Everything after that becomes the transaction note
- Transactions with ambiguous account matches are marked with `!`
- Each transaction gets a "Revert" button to undo if needed

**Examples:**

1. Simple two-leg transaction:
   ```
   1234 20 Restau 中饭
   ```
   Generates:
   ```beancount
   2024-01-10 * "" "中饭"
       Assets:Savings:BOC1234 -20.00 CNY
       Expenses:Food:Restaurant 20.00 CNY
   ```

2. Multi-leg transaction:
   ```
   1234 48.12 in:alibaba 1.88 fruit 水果：西瓜 菠萝蜜
   ```
   Generates:
   ```beancount
   2024-01-10 * "" "水果：西瓜 菠萝蜜"
       Assets:Savings:BOC1234 -48.12 CNY
       Income:Bonus:Alibaba -1.88 CNY
       Expenses:Food:Fruit 50.00 CNY
   ```

### Commands

- `/start` - Start the bot
- `/help` - Show available commands
- `/reload` - Reload account list from `accounts.list` file

### Account Completion

The bot uses an `accounts.list` file for fuzzy account matching:

- Generated automatically on first startup from your beancount output file
- Accounts are sorted by usage frequency (most used first)
- Located in the same directory as your `BEANCOUNT_ROOT` file
- Manually edit or regenerate by deleting and restarting the bot

## Development

### Running Tests

```bash
# Using pytest
pytest src/test_bot.py

# Using uv
uv run pytest src/test_bot.py
```

### Building Docker Image

The bot automatically publishes Docker images to GitHub Container Registry on every push to master or version tag.

**Pull pre-built image:**
```bash
docker pull ghcr.io/wogong/beancount-bot:master
```

**Build locally:**
```bash
docker build -t beancount-bot .
```

### Project Structure

```
.
├── src/
│   ├── bot.py           # Main bot code
│   ├── test_bot.py      # Unit tests
│   └── .env.example     # Environment variables template
├── Dockerfile           # Docker image definition
├── docker-compose.yaml  # Docker Compose configuration
└── pyproject.toml       # Python dependencies (uv)
```

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `BOT` | Telegram bot token from BotFather | `123456:ABC-DEF...` |
| `CHAT_ID` | Your Telegram user ID | `123456789` |
| `BEANCOUNT_ROOT` | Path to main beancount file | `/data/main.beancount` |
| `BEANCOUNT_OUTPUT` | Path to output file for new transactions | `/data/transactions.beancount` |
| `CURRENCY` | Default currency | `CNY` or `USD` |
| `PROXY` | Optional HTTP proxy | Leave empty if not needed |

## Credits

- [beancount](https://github.com/beancount/beancount) - Double-entry accounting from text files
- [vim-beancount](https://github.com/nathangrigg/vim-beancount) - Account completion inspiration
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Telegram Bot API wrapper
