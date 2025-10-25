# Beancount Bot

This is a Telegram bot that allows you to add transactions to your Beancount file.

## Steps

### Download repo and use Python

1. Create a new bot with @BotFather and obtain its token.
2. Obtain your UserID with @userinfobot.
3. Download this repo and copy the `src/env.example` file to `src/.env` and update the config file with your own values.
4. Install the required packages with `python3 -m pip install -r requirements.txt`, then run the bot with `python3 src/bot.py`.
5. Or, if you use `uv`, just run `uv run src/bot.py`.

### Docker-Compose
Step 1-4 are same as above, make sure you have docker and docker-compose installed.

5. Update volume paths in docker-compose.yml, then run `docker-compose up`

## Usage

Message the bot and it will reply with the generated transactions or error information.

### Message format

The message format that the bot accepts is as follows:

`{account_from1 amount1} {account_from2 amount2} ... account_to note`

- The `account_from` and `account_to` variables will be used as a query to your accounts. Match algo is basically the same as account completion you use in vim or vscode.
- The first `2n+1`` variables must be separated by a space, and the remaining strings will be treated as the note(can be left empty).
- Transactions that the bot is unsure about will be marked with `!`. (like multiple accounts matched)

example:

1. `1234 20 Restau 中饭` generates

    ```
    2023-07-13 * "" "中饭"
        Assets:Savings:BOC1234 -20.00 CNY
        Expenses:Food:Restaurent
    ```

2. `1234 48.12 in:alibaba 1.88 fruit 水果：西瓜 菠萝蜜` generates

    ```
    2023-07-13 * "" "水果：西瓜 菠萝蜜"
        Assets:Savings:BOC1234 -48.12 CNY
        Income:Bonus:Alibaba -1.88 CNY
        Expenses:Food:Fruit 50.00 CNY
    ```

### Commands

- You can use `/bal 1234` to query the balance of account~'1234'.
- You can use `/pay 2345` to query the monthly payment of account~'2345' in curent year.
- `/reload` tells the bot to re-run `load_file` (see `src/bot.py`, line 117) so that balances, BQL queries, and account lists reflect any ledger edits you made outside the bot. The response will echo any loader errors, split across multiple Telegram messages if needed to avoid API limits.
- Add any other commands you like, remember to add corresponding commands in your Makefile and `src/bot.py`.

### Ledger reload & validation feedback

- When the bot starts, `AccountsData` immediately runs `load_file` and logs each loader error (with filename:line information) to the console, making it easier to diagnose ledger issues before chatting with the bot.
- Running `/reload` later shows the same loader output in-chat, prefixed with `load_file (line 117)` so you know exactly which call produced the diagnostics.

### Auto balance assertions

- Configure day-of-month balance assertions inside `src/config.yaml` under the `auto_balance` section. Each entry specifies the date(s) and the accounts that should receive `balance` directives. Example:

```yaml
auto_balance:
  ledger: /path/to/ledger.beancount   # optional, defaults to BEANCOUNT_OUTPUT then BEANCOUNT_ROOT
  interval_seconds: 3600              # optional, how often to check schedules
  entries:
    - date: 1
      description: "Credit cards bill day"
      accounts:
        - account: Liabilities:CreditCard:ICBC:CUP-5600
          currency: CNY
          balance: "-0.00"
        - account: Assets:Virtual:WeChat
          currency: CNY
    - date: 15
      accounts:
        - account: Assets:Crypto:Wallet
          currency: BTC
          api_function: crypto_balance.fetch_wallet_balance  # dotted import or built-in fetcher name
          args:
            address: "0xabc..."
            precision: 8
        - account: Assets:Crypto:BNBWallet
          currency: BNB
          api_function: crypto_balance.fetch_bnb_balance_on_bsc
          args:
            address: "0xabc..."
        - account: Assets:Crypto:BNBWallet:USDT
          currency: USDT
          api_function: crypto_balance.fetch_usdt_balance_on_bsc
          args:
            address: "0xabc..."
        - account: Assets:Crypto:BNBWallet:USDC
          currency: USDC
          api_function: crypto_balance.fetch_usdc_balance_on_bsc
          args:
            address: "0xabc..."
```

- The bot runs the auto-balance job once at startup and then every configured interval (default daily). When the current date matches an entry, it appends the balance assertion to the configured ledger file and notifies the owner in Telegram. Duplicate lines for the same date/account are skipped if they already exist in the ledger.
- For accounts that can fetch balances from an API (e.g., crypto wallets), specify `api_function` plus an `args` mapping. Functions can be either built-in (see `auto_balance.py`) or any dotted import path that returns the numeric balance; the bot awaits coroutine results as well. Omit `api_function` to fall back to the static `balance` value (default `0`).
- The auto-balance scheduler uses python-telegram-bot’s JobQueue subsystem. Make sure the dependency is installed with the `job-queue` extra (`pip install "python-telegram-bot[job-queue]"` or run `uv sync` with the provided requirements).
- `src/crypto_balance.py` contains example fetchers (`fetch_wallet_balance`, `fetch_bnb_balance_on_bsc`, `fetch_usdt_balance_on_bsc`, `fetch_usdc_balance_on_bsc`) that you can copy and extend to integrate with your real APIs. Network endpoints are read from `.env` (e.g., set `BSC_ENDPOINT=https://bsc-mainnet.infura.io/v3/<project_id>`).

## TODO

- [x] fuzzy match
- [x] docker deployment
- [x] support multiple legs
- [x] unit test
- [x] add commands to run `bean-query`
- [x] reload beancount file

## Credits
- [beancount](https://github.com/beancount/beancount)
- [vim-beancount](https://github.com/nathangrigg/vim-beancount)
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
