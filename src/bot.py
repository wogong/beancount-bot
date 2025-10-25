import os
import re
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional, Sequence
from functools import wraps

from beancount.loader import load_file
from beancount.core import data
from beancount.core.inventory import Inventory
from beanquery import Connection

from telegram import ForceReply, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, CallbackContext, ContextTypes, ExtBot, MessageHandler, filters

from dotenv import load_dotenv
import yaml

from auto_balance import (
    AutoBalanceManager,
    AutoBalanceConfig,
    load_auto_balance_config,
    default_fetcher_registry,
)

load_dotenv()
SCRIPT_DIR = Path(__file__).resolve().parent
BEANCOUNT_ROOT = os.getenv("BEANCOUNT_ROOT")
BEANCOUNT_OUTPUT = os.getenv("BEANCOUNT_OUTPUT")
BOT = os.getenv("BOT")
CURRENCY = os.getenv("CURRENCY")
CHAT_ID = os.getenv("CHAT_ID")
ALLOWED_USERS = [int(CHAT_ID)]
PROXY = os.getenv("PROXY")
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "config.yaml"
CONFIG_PATH = Path(os.getenv("BOT_CONFIG", DEFAULT_CONFIG_PATH)).expanduser()
BQL_ARGUMENT_TOKEN = "[args]"
TELEGRAM_MESSAGE_LIMIT = 4096
AMOUNT_TOKEN_PATTERN = re.compile(r'^([+-]?(?:\d+(?:\.\d+)?|\.\d+))([A-Za-z]*)$')

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def load_bot_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        logger.info("No config file at %s; using defaults only.", CONFIG_PATH)
        return {}

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
            return yaml.safe_load(config_file) or {}
    except Exception as error:
        logger.error("Failed to read %s: %s", CONFIG_PATH, error)
        return {}


@dataclass(frozen=True)
class BQLQueryDefinition:
    name: str
    sql: str
    description: Optional[str] = None


DEFAULT_BQL_QUERIES: Dict[str, BQLQueryDefinition] = {
    "pay": BQLQueryDefinition(
        name="pay",
        sql=(
            "select account, month(date) as month, sum(position) "
            "from year=2025 where account ~ [args] and number<0 "
            "group by account, month order by month desc"
        ),
        description="Monthly outgoing totals for matching accounts (2025).",
    ),
}


def _coerce_query_definition(alias: str, raw_value) -> Optional[BQLQueryDefinition]:
    if isinstance(raw_value, str):
        sql = raw_value
        description = None
    elif isinstance(raw_value, dict):
        sql = raw_value.get("query") or raw_value.get("sql")
        description = raw_value.get("description")
    else:
        logger.warning("Ignoring query alias %s: unsupported config value", alias)
        return None

    if not sql:
        logger.warning("Ignoring query alias %s: missing SQL text", alias)
        return None

    return BQLQueryDefinition(name=alias, sql=str(sql), description=description)


def load_bql_query_definitions(config_data: Optional[Dict[str, Any]] = None) -> Dict[str, BQLQueryDefinition]:
    definitions = dict(DEFAULT_BQL_QUERIES)

    if not config_data:
        return definitions

    queries = config_data.get("queries") or {}
    if not isinstance(queries, dict):
        logger.warning("Config file %s has invalid 'queries' section; expected mapping.", CONFIG_PATH)
        return definitions

    for alias, raw_value in queries.items():
        normalized_alias = alias.lower()
        definition = _coerce_query_definition(normalized_alias, raw_value)
        if definition:
            definitions[normalized_alias] = definition

    return definitions

BOT_CONFIG = load_bot_config()
BQL_QUERY_DEFINITIONS = load_bql_query_definitions(BOT_CONFIG)

AUTO_BALANCE_CONFIG = load_auto_balance_config(BOT_CONFIG, CURRENCY or 'CNY')
AUTO_BALANCE_LEDGER = (
    os.getenv('AUTO_BALANCE_LEDGER')
    or (AUTO_BALANCE_CONFIG.ledger if AUTO_BALANCE_CONFIG.ledger else None)
    or BEANCOUNT_OUTPUT
    or BEANCOUNT_ROOT
)
AUTO_BALANCE_LEDGER_PATH = Path(AUTO_BALANCE_LEDGER).expanduser() if AUTO_BALANCE_LEDGER else None
AUTO_BALANCE_MANAGER: Optional[AutoBalanceManager] = None
if AUTO_BALANCE_LEDGER_PATH and AUTO_BALANCE_CONFIG.has_entries():
    AUTO_BALANCE_MANAGER = AutoBalanceManager(
        config=AUTO_BALANCE_CONFIG,
        ledger_path=AUTO_BALANCE_LEDGER_PATH,
        fetcher_registry=default_fetcher_registry(),
    )


def format_loader_error(error) -> str:
    """Return a concise description of a beancount loader error."""
    message = getattr(error, 'message', str(error))
    source = getattr(error, 'source', None)
    filename = None
    lineno = None

    if isinstance(source, dict):
        filename = source.get('filename') or ''
        lineno = source.get('lineno')

    location = ''
    if filename:
        location = str(filename)
        if lineno:
            location = f'{location}:{lineno}'
    elif lineno:
        location = f'line {lineno}'

    if location:
        return f'{location} - {message}'
    return message


def format_loader_errors(errors: Sequence) -> str:
    return '\n'.join(format_loader_error(error) for error in errors)


async def reply_with_chunks(message, text: str, chunk_size: int = TELEGRAM_MESSAGE_LIMIT - 200) -> None:
    """Reply to a Telegram message, splitting content to avoid length limits."""
    if not text or not message:
        return

    chunk_size = max(1, chunk_size)
    for start in range(0, len(text), chunk_size):
        await message.reply_text(text[start:start + chunk_size])


class AccountsData:
    """Custom class for chat_data. Here we store data per message."""

    def __init__(self) -> None:
        self.accounts = set()
        self.balances: Dict[str, Inventory] = {}
        self.bql_queries = dict(BQL_QUERY_DEFINITIONS)
        self.bql_connection: Optional[Connection] = None
        self.last_errors: Sequence = []
        self.reload()

    def reload(self):
        entries, errors, options = load_file(BEANCOUNT_ROOT)
        accounts = set()

        for entry in entries:
            if isinstance(entry, data.Open):
                accounts.add(entry.account)
            if isinstance(entry, data.Close):
                accounts.discard(entry.account)

        self.accounts = accounts
        self.balances = build_account_balances(entries)
        self.bql_connection = build_bql_connection(entries, errors, options)
        self.last_errors = errors or []
        self._log_loader_errors(self.last_errors)
        logger.info('Finished initiating accounts set, balances, and BQL context.')
        return self.last_errors

    @staticmethod
    def _log_loader_errors(errors: Sequence) -> None:
        if not errors:
            logger.info('Ledger loaded without errors.')
            return

        logger.error('Ledger loaded with %d error(s).', len(errors))
        for error in errors:
            logger.error('Ledger error: %s', format_loader_error(error))

    def run_bql_query(self, alias: str, arguments: str):
        if not self.bql_connection:
            raise RuntimeError('BQL connection is not available.')

        definition = self.bql_queries.get(alias)
        if not definition:
            raise KeyError(alias)

        query_text = render_bql_query(definition, arguments)
        cursor = self.bql_connection.cursor()
        cursor.execute(query_text)
        description = cursor.description or []
        rows = cursor.fetchall()
        return description, rows


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
        "/bal <account> - Check current account balance",
        "/reload - Reload the ledger file",
    ]

    bot_data = getattr(context, 'bot_data', None)
    bql_aliases = []
    if bot_data and hasattr(bot_data, 'bql_queries'):
        bql_aliases = sorted(bot_data.bql_queries.keys())

    if bql_aliases:
        lines.append("/bql <alias> [args] - Run a configured ledger query")
        lines.append("Shortcut queries: " + ', '.join(f"/{alias}" for alias in bql_aliases))

    await update.message.reply_text('\n'.join(lines))

@restricted
async def bal(update: Update, context: CustomContext) -> None:
    """Return the balance for the account matching the provided argument."""
    argument = ' '.join(context.args).strip()
    if argument == '':
        await update.message.reply_text('account is required')
        return

    accounts_data = context.bot_data
    account, ambiguous = get_account(argument, accounts_data.accounts)

    if account == 'TODO':
        await update.message.reply_text(f'No account matched "{argument}".')
        return

    balance = accounts_data.balances.get(account)
    balance_text = format_inventory(balance)
    prefix = 'Multiple matches found, showing first.\n' if ambiguous else ''
    await update.message.reply_text(f"{prefix}{account}: {balance_text}")


@restricted
async def bql(update: Update, context: CustomContext) -> None:
    """Execute a configured bean-query by alias."""
    if not context.args:
        await update.message.reply_text('Usage: /bql <query_alias> [args]')
        return

    alias = context.args[0].lower()
    arguments = ' '.join(context.args[1:]).strip()
    await _send_bql_response(update, context, alias, arguments)


@restricted
async def reload_ledger(update: Update, context: CustomContext) -> None:
    """Reload the ledger file so balances reflect the latest entries."""
    message = update.effective_message
    if not message:
        return

    accounts_data = context.bot_data
    try:
        errors = accounts_data.reload()
    except Exception as exc:
        logger.exception('Failed to reload ledger.')
        await message.reply_text(f'Ledger reload failed: {exc}')
        return

    response_lines = ['Ledger reloaded via load_file (line 117).']
    if errors:
        error_block = format_loader_errors(errors)
        response_lines.append(f'{len(errors)} error(s) reported:')
        if error_block:
            response_lines.append(error_block)
    else:
        response_lines.append('No loader errors were reported.')

    await reply_with_chunks(message, '\n'.join(response_lines))


def build_bql_alias_handler(alias: str):
    @restricted
    async def handler(update: Update, context: CustomContext) -> None:
        arguments = ' '.join(context.args).strip()
        await _send_bql_response(update, context, alias, arguments)

    handler.__name__ = f'bql_alias_{alias}'
    return handler


async def _send_bql_response(update: Update, context: CustomContext, alias: str, arguments: str) -> None:
    accounts_data = context.bot_data
    message = update.effective_message
    if not message:
        return

    if not getattr(accounts_data, 'bql_connection', None):
        await message.reply_text('BQL queries are not configured on this bot.')
        return

    try:
        description, rows = accounts_data.run_bql_query(alias, arguments)
    except KeyError:
        await message.reply_text(f'Unknown query alias "{alias}".')
        return
    except ValueError as exc:
        await message.reply_text(str(exc))
        return
    except Exception as exc:
        logger.exception('Failed to run query %s', alias)
        await message.reply_text(f'Failed to run query: {exc}')
        return

    result_text = format_bql_result(description, rows)
    await message.reply_text(result_text)

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


def build_bql_connection(entries, errors, options) -> Optional[Connection]:
    try:
        connection = Connection()
        connection.attach('beancount://', entries=entries, errors=errors, options=options)
        return connection
    except Exception as exc:
        logger.error('Unable to initialize beanquery connection: %s', exc)
        return None


def sanitize_bql_argument(argument: str) -> str:
    escaped = argument.replace("'", "''")
    return f"'{escaped}'"


def render_bql_query(definition: BQLQueryDefinition, user_arguments: str) -> str:
    query = definition.sql
    if BQL_ARGUMENT_TOKEN in query:
        if not user_arguments:
            raise ValueError('This query requires an argument.')
        sanitized = sanitize_bql_argument(user_arguments)
        return query.replace(BQL_ARGUMENT_TOKEN, sanitized)
    if user_arguments:
        raise ValueError('This query does not take any arguments.')
    return query


def format_bql_value(value) -> str:
    if value is None:
        return ''
    if isinstance(value, Decimal):
        return format(value.normalize(), 'f')
    return str(value)


def format_bql_result(description: Sequence, rows: Sequence[Sequence]) -> str:
    if not rows:
        return 'No results.'

    headers = [getattr(column, 'name', str(column)) for column in (description or [])]
    sample_row = rows[0] if rows else []
    if not headers:
        headers = [f'col_{i + 1}' for i in range(len(sample_row))]

    str_rows = [[format_bql_value(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in str_rows:
        for index, cell in enumerate(row):
            if index < len(widths):
                widths[index] = max(widths[index], len(cell))
            else:
                widths.append(len(cell))

    if len(headers) < len(widths):
        next_index = len(headers)
        for _ in range(len(widths) - len(headers)):
            next_index += 1
            headers.append(f'col_{next_index}')

    def format_line(values):
        return ' | '.join(value.ljust(widths[idx]) for idx, value in enumerate(values))

    separator = '-+-'.join('-' * width for width in widths)
    lines = [format_line(headers), separator]
    lines.extend(format_line(row) for row in str_rows)
    return '\n'.join(lines)


def build_account_balances(entries) -> Dict[str, Inventory]:
    """Aggregate balances for every account present in the ledger entries."""
    balances: Dict[str, Inventory] = {}

    for entry in entries:
        if isinstance(entry, data.Transaction):
            for posting in entry.postings:
                if posting.units is None:
                    continue
                balances.setdefault(posting.account, Inventory()).add_amount(posting.units)

    return balances


def format_inventory(inventory: Optional[Inventory]) -> str:
    """Render a Beancount inventory as a human readable string."""
    if inventory is None or inventory.is_empty():
        return '0'

    positions = sorted(
        (position for position in inventory if position.units),
        key=lambda position: position.units.currency,
    )

    formatted_amounts = []
    for position in positions:
        amount = position.units
        number = format(amount.number.normalize(), 'f')
        formatted_amounts.append(f"{number} {amount.currency}")

    return ', '.join(formatted_amounts)


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
        pending_transactions = context.chat_data.setdefault('pending_transactions', {})
        pending_transactions[sent_message.message_id] = transactions


@restricted
async def revert_transaction(update: Update, context: CustomContext) -> None:
    query = update.callback_query
    if query is None or query.message is None:
        return

    pending_transactions = context.chat_data.get('pending_transactions', {})
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


async def auto_balance_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    if not AUTO_BALANCE_MANAGER:
        return

    additions, errors = await AUTO_BALANCE_MANAGER.process_due_entries()

    for account, exc in errors:
        logger.error('Auto-balance error for %s: %s', account.account, exc)

    if not additions:
        return

    lines = ['Auto-balance entries added:']
    for result in additions:
        amount_text = result.account.format_amount(result.amount)
        lines.append(f"- {result.account.account}: {amount_text} {result.account.currency}")

    try:
        await context.bot.send_message(chat_id=int(CHAT_ID), text='\n'.join(lines))
    except Exception as exc:  # pragma: no cover - network failure
        logger.error('Failed to send auto-balance notification: %s', exc)


def main() -> None:
    context_types = ContextTypes(context=CustomContext, bot_data=AccountsData)

    """Start the bot."""
    # Create the Application and pass it your bot's token.
    if len(PROXY) > 5:
        logging.info(f'use proxy {PROXY}')
        application = Application.builder().token(BOT).proxy(PROXY).get_updates_proxy(PROXY).context_types(context_types).build()
    else:
        application = Application.builder().token(BOT).context_types(context_types).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(CommandHandler("bal", bal))
    application.add_handler(CommandHandler("reload", reload_ledger))
    application.add_handler(CommandHandler("bql", bql))
    for alias in BQL_QUERY_DEFINITIONS:
        application.add_handler(CommandHandler(alias, build_bql_alias_handler(alias)))
    application.add_handler(CallbackQueryHandler(revert_transaction, pattern="^revert_transaction$"))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, callback = bean))

    # Run the bot until the user presses Ctrl-C
    logger.info('Starting bot.')

    if AUTO_BALANCE_MANAGER and AUTO_BALANCE_MANAGER.config.has_entries() and application.job_queue:
        interval = max(60, AUTO_BALANCE_MANAGER.config.interval_seconds)
        application.job_queue.run_once(auto_balance_job, when=0, name="auto_balance_startup")
        application.job_queue.run_repeating(auto_balance_job, interval=interval, first=interval, name="auto_balance")

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
