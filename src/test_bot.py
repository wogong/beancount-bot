import pytest
from beancount.loader import load_string

from bot import (
    CURRENCY,
    build_account_balances,
    format_inventory,
    get_leg_num,
    parse_amount_currency,
    parse_message,
)

data_leg_num = [
   ("xxx 4.5 5587", 1),
   ("2739 4.5sgd 5587", 1),
   ("2739 4.5usd in:cup 0.5 5587", 2),
   ("2739 4.5 in:cup 0.5 9423 1.0 5587 还款", 3),
]

data_currency = [
        ("2.20", ("2.20", CURRENCY)),
        ("4.5sgd", ("4.5","SGD")),
        ("4USD", ("4","USD")),
        ]

data_notes = [
   ("xxx 4.5 5587", ""),
   ("xxx 4.5 5587 test", "test"),
   ("2739 4.5usd in:cup 0.5 5587 test1 test2", "test1 test2"),
   ("2739 4.5usd in:cup 0.5 5587 12test中文 12test2", "12test中文 12test2"),
]

data_legs = [
   ("xxxx 4.5 xxxx", [('xxxx', -4.5, CURRENCY), ('xxxx', 4.5, CURRENCY)]),
   ("2739 4.5 9423 2.3 yyyy", [('2739', -4.5, CURRENCY), ('9423', -2.3, CURRENCY), ('yyyy', 6.8, CURRENCY)]),
   ("2739 4.5 9423 2.3 ecard 5 yyyy", [('2739', -4.5, CURRENCY), ('9423', -2.3, CURRENCY), ('ecard', -5.0, CURRENCY), ('yyyy', 11.8, CURRENCY)]),
]

LEDGER_SNIPPET = """
option "title" "Test Ledger"
option "operating_currency" "USD"
1970-01-01 open Assets:Cash USD
1970-01-01 open Expenses:Food USD
1970-01-01 open Income:Salary USD

2024-01-01 * "Salary"
  Assets:Cash         100 USD
  Income:Salary      -100 USD

2024-01-05 * "Dinner"
  Expenses:Food        30 USD
  Assets:Cash         -30 USD
"""

LEDGER_MULTI_CURRENCY = """
option "title" "Multi Ledger"
option "operating_currency" "USD"
1970-01-01 open Assets:Wallet USD, CNY
1970-01-01 open Income:Salary USD, CNY

2024-01-10 * "Salary"
  Assets:Wallet        50 USD
  Income:Salary       -50 USD

2024-01-20 * "Bonus"
  Assets:Wallet       200 CNY
  Income:Salary      -200 CNY
"""

class Test_Beanbot():
    @pytest.mark.parametrize("msg, expected", data_leg_num)
    def test_get_leg_num(self, msg, expected):
        assert get_leg_num(msg.split()) == expected

    @pytest.mark.parametrize("string, expected", data_currency)
    def test_parse_amount_currency(self, string, expected):
        assert parse_amount_currency(string) == expected

    @pytest.mark.parametrize("msg, expected", data_notes)
    def test_parse_message_notes(self, msg, expected):
        _, notes = parse_message(msg)
        assert notes == expected

    @pytest.mark.parametrize("msg, expected", data_legs)
    def test_parse_message_legs(self, msg, expected):
        legs, _ = parse_message(msg)
        print(legs)
        assert legs == expected

    def test_build_account_balances(self):
        entries, _, _ = load_string(LEDGER_SNIPPET)
        balances = build_account_balances(entries)

        assert format_inventory(balances['Assets:Cash']) == '70 USD'
        assert format_inventory(balances['Expenses:Food']) == '30 USD'

    def test_format_inventory_multiple_currencies(self):
        entries, _, _ = load_string(LEDGER_MULTI_CURRENCY)
        balances = build_account_balances(entries)

        assert format_inventory(balances['Assets:Wallet']) == '200 CNY, 50 USD'
