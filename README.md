# Beancount Bot

This is a Telegram bot that allows you to add transactions to your Beancount file.

## Steps

### Download repo and use Python

1. Create a new bot with @BotFather and obtain its token.
2. Obtain your UserID with @userinfobot.
3. Download this repo and copy the config-example.py file to config.py and update the config file with your own values.
4. Install the required packages with `python3 -m pip install -r requirements.txt`.
5. Run the bot with `python3 beanbot.py`.

### Docker-Compose
Step 1-3 are same as above, make sure you have docker and docker-compose installed.

4. Just run `docker-compose up`

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
## TODO

- [x] fuzzy match
- [x] docker deployment
- [x] support multiple legs
- [ ] unit test
- [ ] reload beancount file

## Credits
- [beancount](https://github.com/beancount/beancount)
- [vim-beancount](https://github.com/nathangrigg/vim-beancount)
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)