import os
import re
import logging
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from functools import wraps

from telegram import ForceReply, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, CallbackContext, ContextTypes, ExtBot, MessageHandler, filters

from dotenv import load_dotenv

load_dotenv()
SCRIPT_DIR = Path(__file__).resolve().parent
BEANCOUNT_ROOT = os.getenv("BEANCOUNT_ROOT")
BEANCOUNT_OUTPUT = os.getenv("BEANCOUNT_OUTPUT")
BOT = os.getenv("BOT")
CURRENCY = os.getenv("CURRENCY")
CHAT_ID = os.getenv("CHAT_ID")
ALLOWED_USERS = [int(CHAT_ID)]
PROXY = os.getenv("PROXY")
AMOUNT_TOKEN_PATTERN = re.compile(r'^([+-]?(?:\d+(?:\.\d+)?|\.\d+))([A-Za-z]*)$')

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
        self.accounts = set()
        self.load_accounts_from_file()

    def load_accounts_from_file(self):
        """Load accounts from accounts.list file."""
        accounts_file = Path(BEANCOUNT_ROOT).parent / "accounts.list"
        if accounts_file.exists():
            try:
                with accounts_file.open('r', encoding='utf-8') as f:
                    self.accounts = set(line.strip() for line in f if line.strip())
                logger.info('Loaded %d accounts from accounts.list', len(self.accounts))
            except Exception as e:
                logger.error('Failed to load accounts.list: %s', e)
                self.accounts = set()
        else:
            logger.warning('accounts.list not found, will be generated on first use')
            self.accounts = set()

    def reload(self):
        """Reload accounts from file."""
        self.load_accounts_from_file()


class CustomContext(CallbackContext[ExtBot, dict, dict, AccountsData]):
    """Custom class for context."""
    """Building beancount account set."""

    def __init__(self, application: Application, chat_id: int = None, user_id: int = None):
        super().__init__(application=application, chat_id=chat_id, user_id=user_id)
        self._message_id: Optional[int] = None


def restricted(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ALLOWED_USERS:
            print(f"Unauthorized access, User ID: {user_id}")
            effective_message = update.effective_message
            if update.callback_query:
                await update.callback_query.answer()
            if effective_message:
                await effective_message.reply_text('Sorry, you do not have permission to use this command.')
            return
        return await func(update, context, *args, **kwargs)
    return wrapped


# Define a few command handlers. These usually take the two arguments update and
# context.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        reply_markup=ForceReply(selective=True),
    )

@restricted
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    lines = [
        "Available commands:",
        "/start - Start the bot",
        "/help - Show this help message",
        "/reload - Reload accounts from accounts.list",
    ]

    bot_data = getattr(context, 'bot_data', None)

    await update.message.reply_text('\n'.join(lines))


@restricted
async def reload_ledger(update: Update, context: CustomContext) -> None:
    """Reload accounts from accounts.list file."""
    message = update.effective_message
    if not message:
        return

    accounts_data = context.bot_data
    try:
        accounts_data.reload()
        await message.reply_text(f'Reloaded {len(accounts_data.accounts)} accounts from accounts.list')
    except Exception as exc:
        logger.exception('Failed to reload accounts.')
        await message.reply_text(f'Accounts reload failed: {exc}')


def get_leg_num(data)->int:
    """
    Returns the number of legs in the given data.

    Args:
        data (list): A list of data.

    Returns:
        int: The number of legs in the data.
    
    Examples:
        '5600 13.12 ccc 小米编织数据线 3A' -> 1
        '5600 13.12 Jdou 6 ccc 小米编织数据线 3A' -> 2
        '5600 13.12 Jdou 6 ecard 5 ccc 小米编织数据线 3A' -> 3
    """
    n = 0
    while 2 * n + 1 < len(data) - 1 and AMOUNT_TOKEN_PATTERN.match(data[2 * n + 1]):
        n += 1
    return n


def get_account(base, accounts):
    """
    Get the account matching the given base from the list of accounts.

    Args:
        base (str): The base account to match.
        accounts (list): The list of accounts to search.

    Returns:
        tuple: A tuple containing the matched account and a flag indicating if multiple matches were found.
               If no match is found, the tuple contains a placeholder string 'TODO' and a flag of 1.
               If a single match is found, the tuple contains the matched account and a flag of 0.
               If multiple matches are found, the tuple contains the first matched account and a flag of 1.
    """
    pattern = re.compile('^.*' + re.sub(':', '.*:.*', base) + '.*', re.IGNORECASE)
    r = list(filter(pattern.match, accounts))
    n = len(r)
    if n == 0:
        return 'TODO', 1
    elif n == 1:
        return r[0], 0
    else:
        return r[0], 1


def parse_amount_currency(string):
    """
    Parses a string to extract the amount and currency.

    Args:
        string (str): The string to be parsed.

    Returns:
        tuple: A tuple containing the amount and currency extracted from the string.

    Raises:
        None

    """
    match = AMOUNT_TOKEN_PATTERN.match(string)
    if not match:
        print('Invalid amount format')
        return None

    amount = match.group(1)
    currency = match.group(2) if match.group(2) else CURRENCY
    return amount, currency.upper()


def parse_message(msg):
    """
    Parses a message and returns a list of legs and a note.

    Args:
        msg (str): The message to parse.

    Returns:
        tuple: A tuple containing a list of legs and a note.
            The list of legs is a list of tuples, where each tuple contains
            the account, amount, and currency for a leg.
            The note is a string containing any additional notes.

    Example:
        >>> msg = "account1 10USD account2 -10USD"
        >>> parse_message(msg)
        ([
            ('account1', -10.0, 'USD'),
            ('account2', 10.0, 'USD')
        ], '')
    """
    data = msg.split()
    leg_num = get_leg_num(data)
    legs = []
    sum_amounts = 0.0
    currency = CURRENCY
    for i in range(0, leg_num):
        account = data[2*i]
        parsed = parse_amount_currency(data[2 * i + 1])
        if not parsed:
            raise ValueError('Invalid amount format')
        amount, currency = parsed
        sum_amounts = sum_amounts + float(amount)
        leg = (account, -float(amount), currency)
        legs.append(leg)
    leg_to = (data[2 * leg_num], sum_amounts, currency)
    legs.append(leg_to)
    note_ = data[2 * leg_num + 1:]
    note = ' '.join(note_)
    return legs, note


@restricted 
async def bean(update: Update, context: CustomContext) -> None:
    chat_id = update.message.chat.id
    if (chat_id != int(CHAT_ID)):
        await update.message.reply_text('You are not the owner of this bot.')
    else:
        message = update.message.text
        accounts = context.bot_data.accounts
        try:
            legs, note = parse_message(message)
        except Exception as e:
            print(str(e))
            response = f'error, {e}'
            await update.message.reply_text(response)
            return
        flags = 0
        transactions = ''
        for leg in legs:
            _account, _amount, currency = leg
            amount = Decimal(float(_amount)).quantize(Decimal('0.00'))
            account, flag = get_account(_account, accounts)
            flags = flags + flag
            transactions = transactions + '\n    ' + account + ' ' + str(amount) + ' ' + currency

        flag_mark = '!' if flags > 0 else '*'
        date = datetime.now().strftime("%Y-%m-%d")

        transactions = f"""{date} {flag_mark} "" "{note}"{transactions}
"""
        with open(BEANCOUNT_OUTPUT, 'a+', encoding='utf-8') as f:
            f.write(transactions)
        print(transactions)
        response = transactions
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(text='Revert', callback_data='revert_transaction')]]
        )
        sent_message = await update.message.reply_text(response, reply_markup=keyboard)
        pending_transactions = context.chat_data.setdefault('pending_transactions', OrderedDict())
        pending_transactions[sent_message.message_id] = transactions

        # Limit to most recent 50 transactions
        MAX_PENDING = 50
        if len(pending_transactions) > MAX_PENDING:
            # Remove oldest
            oldest_key = next(iter(pending_transactions))
            pending_transactions.pop(oldest_key)


@restricted
async def revert_transaction(update: Update, context: CustomContext) -> None:
    query = update.callback_query
    if query is None or query.message is None:
        return

    pending_transactions = context.chat_data.get('pending_transactions', OrderedDict())
    transaction = pending_transactions.get(query.message.message_id)

    if transaction is None:
        await query.answer(text='Nothing to revert.', show_alert=True)
        await query.edit_message_reply_markup(reply_markup=None)
        return

    try:
        with open(BEANCOUNT_OUTPUT, 'r+', encoding='utf-8') as ledger:
            content = ledger.read()
            if not content.endswith(transaction):
                await query.answer(text='Cannot revert: ledger has changed.', show_alert=True)
                return
            ledger.seek(0)
            ledger.truncate()
            ledger.write(content[:-len(transaction)])
    except FileNotFoundError:
        await query.answer(text='Cannot revert: ledger file missing.', show_alert=True)
        return

    pending_transactions.pop(query.message.message_id, None)
    await query.answer(text='Transaction reverted.')
    updated_text = f"{query.message.text}\n\nReverted." if query.message.text else "Reverted."
    await query.edit_message_text(updated_text)


def generate_accounts_list():
    """Generate accounts.list file from beancount output, ordered by usage frequency."""
    accounts_file = Path(BEANCOUNT_ROOT).parent / "accounts.list"

    # If file already exists, skip generation
    if accounts_file.exists():
        logger.info('accounts.list already exists, skipping generation')
        return

    logger.info('Generating accounts.list from beancount output...')

    # Count account usage from the output file
    account_counts = {}

    try:
        if not os.path.exists(BEANCOUNT_OUTPUT):
            logger.warning('BEANCOUNT_OUTPUT file not found: %s', BEANCOUNT_OUTPUT)
            return

        with open(BEANCOUNT_OUTPUT, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Match account lines in transactions (lines starting with account names)
                # Typical format: "    Assets:Cash  100.00 CNY"
                if line and not line.startswith(('*', '!', ';', 'option', 'plugin', 'include')):
                    # Try to extract account name (before amount or at start of posting line)
                    parts = line.split()
                    if parts:
                        # Check if first part looks like an account (contains colons)
                        potential_account = parts[0]
                        if ':' in potential_account and not potential_account.startswith(('20', '19')):
                            # It's likely an account name
                            account_counts[potential_account] = account_counts.get(potential_account, 0) + 1

        if not account_counts:
            logger.warning('No accounts found in BEANCOUNT_OUTPUT')
            return

        # Sort by usage count (descending), then alphabetically
        sorted_accounts = sorted(account_counts.items(), key=lambda x: (-x[1], x[0]))

        # Write to file
        with accounts_file.open('w', encoding='utf-8') as f:
            for account, _ in sorted_accounts:
                f.write(f'{account}\n')

        logger.info('Generated accounts.list with %d accounts', len(sorted_accounts))

    except Exception as e:
        logger.error('Failed to generate accounts.list: %s', e)


def main() -> None:
    # Generate accounts.list if it doesn't exist
    generate_accounts_list()

    context_types = ContextTypes(context=CustomContext, bot_data=AccountsData)

    """Start the bot."""
    # Create the Application and pass it your bot's token.
    if PROXY and len(PROXY) > 5:
        logging.info(f'use proxy {PROXY}')
        application = Application.builder().token(BOT).proxy(PROXY).get_updates_proxy(PROXY).context_types(context_types).build()
    else:
        application = Application.builder().token(BOT).context_types(context_types).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(CommandHandler("reload", reload_ledger))

    # Callback query handler for revert button
    application.add_handler(CallbackQueryHandler(revert_transaction, pattern='revert_transaction'))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, callback = bean))

    # Run the bot until the user presses Ctrl-C
    logger.info('Starting bot.')

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
