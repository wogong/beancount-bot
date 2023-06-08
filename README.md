# beancount bot

Using telegram bot to add transactions to your beancount file.

## Steps

1. @BotFather new bot and get token.
2. @userinfobot get your UserID.
3. `cp config-example.py config.py`, update config using your own value.
4. `pip install -r requirements.txt`
6. `python beanbot.py`

## Usage

Message to the bot, reply genereted transactions or error information.

### message format

`account_from amount account_to note`

- Variable `account_from` or `account_to` will be used as query to your accounts.
- The first 3 variables must be split with `Space`, the left string will be `note`, can be empty.
- Any generated transactions unsure will be marked as `!`
