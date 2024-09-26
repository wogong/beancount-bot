# Beancount Bot

This is a Telegram bot that allows you to add transactions to your Beancount file.

## Steps

### Download repo and use Python

1. Create a new bot with @BotFather and obtain its token.
2. Obtain your UserID with @userinfobot.
3. Download this repo and copy the `src/env.example` file to `src/.env` and update the config file with your own values.
4. Copy the example Makefile from `beancount_root/Makefile`, maybe you need to update `bean-query` path.
5. Install the required packages with `python3 -m pip install -r requirements.txt`, then run the bot with `python3 src/bot.py`.
5. Or, if you use `uv`, just run `uv run src/bot.py`.

### Docker-Compose
Step 1-4 are same as above, make sure you have docker and docker-compose installed.

5. Just run `docker-compose up`

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
- Add any other commands you like, remember to add corresponding commands in your Makefile and `src/bot.py`.

## TODO

- [x] fuzzy match
- [x] docker deployment
- [x] support multiple legs
- [x] unit test
- [x] add commands to run `bean-query`
- [ ] reload beancount file

## Credits
- [beancount](https://github.com/beancount/beancount)
- [vim-beancount](https://github.com/nathangrigg/vim-beancount)
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)