# Beancount Bot

This is a Telegram bot that allows you to add transactions to your Beancount file.

## Steps

1. Create a new bot with @BotFather and obtain its token.
2. Obtain your UserID with @userinfobot.
3. Copy the config-example.py file to config.py and update the config file with your own values.
4. Install the required packages with `pip install -r requirements.txt`.
5. Run the bot with `python beanbot.py`.

## Usage

Message the bot and it will reply with the generated transactions or error information.

### Message format

The message format that the bot accepts is as follows:

`account_from amount account_to note`

- The `account_from` and `account_to` variables will be used as a query to your accounts.
- The first three variables must be separated by a space, and the remaining string will be treated as the note and can be left empty.
- Transactions that the bot is unsure about will be marked with `!`.

## TODO

- [ ] unit test
- [ ] docker deployment
- [ ] reload beancount file
- [x] fuzzy match