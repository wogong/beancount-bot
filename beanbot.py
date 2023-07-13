#!/usr/bin/env python
# pylint: disable=unused-argument, wrong-import-position
# This program is dedicated to the public domain under the CC0 license.

"""
Simple Bot to reply to Telegram messages.

First, a few handler functions are defined. Then, those functions are passed to
the Application and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.

Usage:
Basic Echobot example, repeats messages.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""

import re
import logging
from datetime import datetime
from decimal import Decimal

from beancount.loader import load_file
from beancount.core import data

from config import *

from telegram import __version__ as TG_VER

try:
    from telegram import __version_info__
except ImportError:
    __version_info__ = (0, 0, 0, 0, 0)  # type: ignore[assignment]

if __version_info__ < (20, 0, 0, "alpha", 1):
    raise RuntimeError(
        f"This example is not compatible with your current PTB version {TG_VER}. To view the "
        f"{TG_VER} version of this example, "
        f"visit https://docs.python-telegram-bot.org/en/v{TG_VER}/examples.html"
    )
from telegram import ForceReply, Update
from telegram.ext import Application, CommandHandler, CallbackContext, ContextTypes, ExtBot, MessageHandler, filters

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class AccountsData:
    """Custom class for chat_data. Here we store data per message."""

    def __init__(self) -> None:
        entries, _, options = load_file(BEANCOUNT_ROOT)
        self.accounts = set()

        for entry in entries:
            if isinstance(entry, data.Open):
                self.accounts.add(entry.account)
            if isinstance(entry, data.Close):
                self.accounts.remove(entry.account)
        logger.info('Finished initiating accounts set.')


class CustomContext(CallbackContext[ExtBot, dict, dict, AccountsData]):
    """Custom class for context."""
    """Building beancount account set."""

    def __init__(self, application: Application, chat_id: int = None, user_id: int = None):
        super().__init__(application=application, chat_id=chat_id, user_id=user_id)
        self._message_id: Optional[int] = None


# Define a few command handlers. These usually take the two arguments update and
# context.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        reply_markup=ForceReply(selective=True),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text("Help!")


def getaccount(base, accounts):
    pattern = re.compile('^.*' + re.sub(':', '.*:.*', base) + '.*', re.IGNORECASE)
    r = list(filter(pattern.match, accounts))
    n = len(r)
    if n == 0:
        return 'TODO', 1
    elif n == 1:
        return r[0], 0
    else:
        return r[0], 1


async def bean(update: Update, context: CustomContext) -> None:
    chat_id = update.message.chat.id
    if (chat_id != int(CHAT_ID)):
        update.message.reply_text('You are not the owner of this bot.')
    message = update.message.text
    accounts = context.bot_data.accounts
    try:
        _from, _amount, _to, *note = message.split()
        note = ' '.join(note)
        account_from, flag_from = getaccount(_from, accounts)
        account_to, flag_to = getaccount(_to, accounts)
        flag_mark = '!' if flag_from + flag_to > 0 else '*'
        amount = -Decimal(float(_amount)).quantize(Decimal('0.00'))
        date = datetime.now().strftime("%Y-%m-%d")

        transactions = f"""{date} {flag_mark} "" "{note}"
    {account_from} {amount} CNY
    {account_to}
"""
        with open(BEANCOUNT_OUTPUT, 'a+') as f:
            f.write(transactions)
        print(transactions)
        response = transactions
    except Exception as e:
        print(str(e))
        response = 'error, {}'.format(str(e))
    await update.message.reply_text(response)


def main() -> None:
    context_types = ContextTypes(context=CustomContext, bot_data=AccountsData)

    """Start the bot."""
    # Create the Application and pass it your bot's token.
    if 'PROXY' in globals():
        application = Application.builder().token(BOT).proxy_url(PROXY).get_updates_proxy_url(PROXY).build()
    else:
        application = Application.builder().token(BOT).context_types(context_types).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, callback = bean))

    # Run the bot until the user presses Ctrl-C
    logger.info('Starting bot.')
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
