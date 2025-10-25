"""Auto-balance helpers for scheduling ledger balance assertions."""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from importlib import import_module
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from zoneinfo import ZoneInfo

DEFAULT_PRECISION = 2
DEFAULT_INTERVAL_SECONDS = 24 * 60 * 60  # once per day


@dataclass(frozen=True)
class DateMatcher:
    """Represents either a specific calendar date or a monthly day."""

    day_of_month: Optional[int] = None
    exact_date: Optional[date] = None

    def matches(self, today: date) -> bool:
        if self.exact_date:
            return today == self.exact_date
        if self.day_of_month is None:
            return False
        return today.day == self.day_of_month


@dataclass
class AutoBalanceAccount:
    account: str
    currency: str
    balance: Decimal = Decimal("0")
    api_function: Optional[str] = None
    args: Dict[str, Any] = field(default_factory=dict)
    precision: int = DEFAULT_PRECISION

    async def resolve_amount(self, fetcher_registry: Dict[str, Callable[..., Any]]) -> Decimal:
        if not self.api_function:
            return self.balance

        fetcher = resolve_fetcher(self.api_function, fetcher_registry)
        result = fetcher(**self.args)
        if inspect.isawaitable(result):
            result = await result  # type: ignore[assignment]
        return coerce_decimal(result)

    def format_amount(self, amount: Decimal) -> str:
        scale = Decimal("1").scaleb(-self.precision)
        quantized = amount.quantize(scale)
        return format(quantized, "f")


@dataclass
class AutoBalanceEntry:
    dates: Sequence[DateMatcher]
    accounts: Sequence[AutoBalanceAccount]
    description: Optional[str] = None

    def is_due(self, today: date) -> bool:
        return any(matcher.matches(today) for matcher in self.dates)


@dataclass
class AutoBalanceConfig:
    entries: Sequence[AutoBalanceEntry]
    timezone: Optional[ZoneInfo]
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS
    ledger: Optional[str] = None

    def has_entries(self) -> bool:
        return bool(self.entries)


@dataclass
class AutoBalanceResult:
    account: AutoBalanceAccount
    amount: Decimal
    line: str


@dataclass
class AutoBalanceManager:
    config: AutoBalanceConfig
    ledger_path: Path
    fetcher_registry: Dict[str, Callable[..., Any]]

    def __post_init__(self) -> None:
        self._last_processed: Dict[Tuple[str, str], date] = {}

    async def process_due_entries(self, now: Optional[datetime] = None) -> Tuple[List[AutoBalanceResult], List[Tuple[AutoBalanceAccount, Exception]]]:
        if not self.config.entries:
            return [], []

        if now is None:
            tz = self.config.timezone
            now = datetime.now(tz) if tz else datetime.now()

        today = now.date()
        additions: List[AutoBalanceResult] = []
        errors: List[Tuple[AutoBalanceAccount, Exception]] = []

        for entry in self.config.entries:
            if not entry.is_due(today):
                continue
            for account in entry.accounts:
                key = (account.account, today.isoformat())
                if self._last_processed.get(key) == today:
                    continue
                if self._has_existing_line(today, account.account):
                    self._last_processed[key] = today
                    continue
                try:
                    amount = await account.resolve_amount(self.fetcher_registry)
                except Exception as exc:  # pragma: no cover
                    errors.append((account, exc))
                    continue

                line = format_balance_line(today, account, amount)
                try:
                    append_balance_line(self.ledger_path, line)
                except Exception as exc:  # pragma: no cover
                    errors.append((account, exc))
                    continue

                self._last_processed[key] = today
                additions.append(AutoBalanceResult(account=account, amount=amount, line=line))

        return additions, errors

    def _has_existing_line(self, target_date: date, account_name: str) -> bool:
        prefix = f"{target_date.isoformat()} balance {account_name}"
        if not self.ledger_path.exists():
            return False

        try:
            with self.ledger_path.open("r", encoding="utf-8") as ledger:
                for raw_line in ledger:
                    if raw_line.strip().startswith(prefix):
                        return True
        except FileNotFoundError:
            return False
        return False


def append_balance_line(ledger_path: Path, line: str) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as ledger:
        ledger.write(line)
        if not line.endswith("\n"):
            ledger.write("\n")


def format_balance_line(entry_date: date, account: AutoBalanceAccount, amount: Decimal) -> str:
    amount_text = account.format_amount(amount)
    return f"{entry_date.isoformat()} balance {account.account} {amount_text} {account.currency}\n"


def coerce_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        return Decimal(value)
    raise ValueError(f"Unsupported balance value type: {type(value)!r}")


def resolve_fetcher(name: str, registry: Dict[str, Callable[..., Any]]) -> Callable[..., Any]:
    if name in registry:
        return registry[name]
    if "." in name:
        module_name, func_name = name.rsplit(".", 1)
        module = import_module(module_name)
        return getattr(module, func_name)
    raise KeyError(f"Unknown balance fetcher '{name}'")


def parse_date_matchers(raw_date: Any) -> List[DateMatcher]:
    matchers: List[DateMatcher] = []
    if raw_date is None:
        return matchers

    if isinstance(raw_date, list):
        for item in raw_date:
            matchers.extend(parse_date_matchers(item))
        return matchers

    if isinstance(raw_date, int):
        if 1 <= raw_date <= 31:
            matchers.append(DateMatcher(day_of_month=raw_date))
        return matchers

    if isinstance(raw_date, str):
        stripped = raw_date.strip()
        if stripped.isdigit():
            value = int(stripped)
            if 1 <= value <= 31:
                matchers.append(DateMatcher(day_of_month=value))
                return matchers
        try:
            exact = date.fromisoformat(stripped)
            matchers.append(DateMatcher(exact_date=exact))
        except ValueError:
            pass
        return matchers

    return matchers


def parse_account(entry: Dict[str, Any], default_currency: str) -> Optional[AutoBalanceAccount]:
    account_name = entry.get("account")
    if not account_name:
        return None
    currency = entry.get("currency") or default_currency
    precision = entry.get("precision", DEFAULT_PRECISION)
    try:
        precision_value = int(precision)
        if precision_value < 0:
            precision_value = DEFAULT_PRECISION
    except (TypeError, ValueError):
        precision_value = DEFAULT_PRECISION

    balance_value = entry.get("balance")
    balance = coerce_decimal(balance_value) if balance_value is not None else Decimal("0")

    api_function = entry.get("api_function")
    args = entry.get("args") or {}
    if not isinstance(args, dict):
        args = {}

    return AutoBalanceAccount(
        account=account_name,
        currency=str(currency),
        balance=balance,
        api_function=api_function,
        args=args,
        precision=precision_value,
    )


def load_auto_balance_config(config_data: Dict[str, Any], default_currency: str) -> AutoBalanceConfig:
    section = config_data.get("auto_balance") or {}
    timezone = None
    interval_seconds = DEFAULT_INTERVAL_SECONDS
    ledger = None
    entries_data: Iterable[Dict[str, Any]] = []

    if isinstance(section, dict):
        timezone_name = section.get("timezone")
        if timezone_name:
            try:
                timezone = ZoneInfo(timezone_name)
            except Exception:
                timezone = None
        interval_seconds = int(section.get("interval_seconds", DEFAULT_INTERVAL_SECONDS))
        ledger_value = section.get("ledger")
        if isinstance(ledger_value, str) and ledger_value.strip():
            ledger = ledger_value.strip()
        entries_data = section.get("entries") or []
    elif isinstance(section, list):
        entries_data = section

    entries: List[AutoBalanceEntry] = []
    for raw_entry in entries_data:
        if not isinstance(raw_entry, dict):
            continue
        matchers = parse_date_matchers(raw_entry.get("date"))
        if not matchers:
            continue
        accounts_data = raw_entry.get("accounts")
        if isinstance(accounts_data, dict):
            accounts_data = [accounts_data]
        if not isinstance(accounts_data, list):
            continue
        accounts: List[AutoBalanceAccount] = []
        for account_entry in accounts_data:
            if not isinstance(account_entry, dict):
                continue
            account = parse_account(account_entry, default_currency)
            if account:
                accounts.append(account)
        if not accounts:
            continue
        entries.append(
            AutoBalanceEntry(
                dates=matchers,
                accounts=accounts,
                description=raw_entry.get("description"),
            )
        )

    return AutoBalanceConfig(entries=entries, timezone=timezone, interval_seconds=interval_seconds, ledger=ledger)


def default_fetcher_registry() -> Dict[str, Callable[..., Any]]:
    return {
        "constant": lambda value="0", **_: Decimal(str(value)),
    }
