import asyncio
import json
from datetime import datetime, time
from pathlib import Path
from decimal import Decimal

import pytest
from beancount.loader import load_string

from auto_balance import (
    AutoBalanceManager,
    load_auto_balance_config,
    parse_date_matchers,
    default_fetcher_registry,
)
from bot import (
    CURRENCY,
    BQLQueryDefinition,
    build_account_balances,
    format_inventory,
    format_bql_result,
    get_leg_num,
    parse_amount_currency,
    parse_message,
    render_bql_query,
)
from crypto_balance import (
    fetch_bnb_balance_on_bsc,
    fetch_eth_balance_on_ethereum,
    fetch_usdt_balance_on_bsc,
    fetch_usdt_balance_on_ethereum,
    fetch_usdc_balance_on_bsc,
    fetch_usdc_balance_on_ethereum,
)

data_leg_num = [
   ("xxx 4.5 5587", 1),
   ("2739 4.5sgd 5587", 1),
   ("2739 4.5usd in:cup 0.5 5587", 2),
   ("2739 4.5 in:cup 0.5 9423 1.0 5587 还款", 3),
   ("1234 -3.37 5587", 1),
]

data_currency = [
        ("2.20", ("2.20", CURRENCY)),
        ("4.5sgd", ("4.5","SGD")),
        ("4USD", ("4","USD")),
        ("-3.37", ("-3.37", CURRENCY)),
        ("-7.5usd", ("-7.5","USD")),
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
   ("1234 -3.37 2345", [('1234', 3.37, CURRENCY), ('2345', -3.37, CURRENCY)]),
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

    def test_render_bql_query_replaces_placeholder(self):
        definition = BQLQueryDefinition(name='test', sql='account ~ [args]')
        result = render_bql_query(definition, "Assets:Cash")
        assert result == "account ~ 'Assets:Cash'"

    def test_render_bql_query_validates_arguments(self):
        definition = BQLQueryDefinition(name='static', sql='select * from postings')
        with pytest.raises(ValueError):
            render_bql_query(definition, 'unexpected')

        needs_args = BQLQueryDefinition(name='needs', sql='account ~ [args]')
        with pytest.raises(ValueError):
            render_bql_query(needs_args, '')

    def test_format_bql_result_produces_table(self):
        class Column:
            def __init__(self, name):
                self.name = name

        columns = [Column('account'), Column('total')]
        rows = [
            ('Assets:Cash', '70 USD'),
            ('Expenses:Food', '30 USD'),
        ]

        table = format_bql_result(columns, rows)
        assert 'account' in table and 'Assets:Cash' in table


def test_parse_date_matchers_supports_day_and_iso():
    from datetime import date

    matchers = parse_date_matchers(["5", "2024-07-15"])
    assert any(m.day_of_month == 5 for m in matchers)
    assert any(m.exact_date == date(2024, 7, 15) for m in matchers)


def test_auto_balance_config_defaults_runtime():
    config_data = {
        'auto_balance': {
            'entries': [
                {
                    'date': 5,
                    'accounts': [{'account': 'Assets:Cash', 'currency': 'USD', 'balance': '0'}],
                }
            ]
        }
    }
    config = load_auto_balance_config(config_data, 'USD')
    assert config.runtime == time(1, 0)


def test_auto_balance_config_uses_runtime_from_config():
    config_data = {
        'auto_balance': {
            'runtime': '05:45',
            'entries': [
                {
                    'date': 5,
                    'accounts': [{'account': 'Assets:Cash', 'currency': 'USD', 'balance': '0'}],
                }
            ]
        }
    }
    config = load_auto_balance_config(config_data, 'USD')
    assert config.runtime == time(5, 45)


def test_auto_balance_manager_appends_balance(tmp_path):
    config_data = {
        'auto_balance': {
            'entries': [
                {
                    'date': 15,
                    'accounts': [
                        {'account': 'Assets:Cash', 'currency': 'USD', 'balance': '0'}
                    ],
                }
            ]
        }
    }
    config = load_auto_balance_config(config_data, 'USD')
    ledger_path = tmp_path / 'auto.beancount'
    manager = AutoBalanceManager(config=config, ledger_path=ledger_path, fetcher_registry=default_fetcher_registry())

    now = datetime(2024, 7, 15, 3, 0, 0)
    additions, errors = asyncio.run(manager.process_due_entries(now=now))

    assert errors == []
    assert len(additions) == 1
    assert ledger_path.read_text(encoding='utf-8').startswith('2024-07-15 balance Assets:Cash 0.00 USD')

    second_run, _ = asyncio.run(manager.process_due_entries(now=now))
    assert second_run == []


def test_auto_balance_manager_uses_api_function(tmp_path):
    def dummy_fetcher(value):
        return value

    config_data = {
        'auto_balance': {
            'entries': [
                {
                    'date': '01',
                    'accounts': [
                        {
                            'account': 'Assets:Crypto:Wallet',
                            'currency': 'BTC',
                            'api_function': 'dummy',
                            'args': {'value': '0.12345678'},
                            'precision': 8,
                        }
                    ],
                }
            ]
        }
    }

    config = load_auto_balance_config(config_data, 'USD')
    ledger_path = tmp_path / 'crypto.beancount'
    manager = AutoBalanceManager(config=config, ledger_path=ledger_path, fetcher_registry={'dummy': dummy_fetcher})

    now = datetime(2024, 7, 1, 0, 0, 0)
    additions, errors = asyncio.run(manager.process_due_entries(now=now))

    assert errors == []
    assert len(additions) == 1
    assert '0.12345678 BTC' in ledger_path.read_text(encoding='utf-8')


def test_fetch_bnb_balance_on_bsc_parses_rpc_response():
    class DummyResponse:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode('utf-8')

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def open_stub(req, timeout):
        body = json.loads(req.data.decode('utf-8'))
        assert body['method'] == 'eth_getBalance'
        assert body['params'][0] == '0x0000000000000000000000000000000000000000'
        return DummyResponse({'jsonrpc': '2.0', 'id': 1, 'result': hex(10**18)})

    balance = fetch_bnb_balance_on_bsc(
        address='0x0000000000000000000000000000000000000000',
        api_key='key',
        opener=open_stub,
    )
    assert balance == Decimal('1')


def _dummy_rpc_response(hex_value):
    class DummyResponse:
        def __init__(self, result_hex):
            self.result_hex = result_hex

        def read(self):
            return json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': self.result_hex}).encode('utf-8')

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    return DummyResponse(hex_value)


def test_fetch_usdt_balance_on_bsc_uses_token_contract():
    captured = {}

    def open_stub(req, timeout):
        body = json.loads(req.data.decode('utf-8'))
        captured['body'] = body
        return _dummy_rpc_response(hex(1230000000000000000))

    balance = fetch_usdt_balance_on_bsc(
        address='0xb794f5ea0ba39494ce839613fffba74279579268',
        api_key='key',
        opener=open_stub,
    )

    params = captured['body']['params']
    assert captured['body']['method'] == 'eth_call'
    assert params[0]['to'].lower() == '0x55d398326f99059ff775485246999027b3197955'
    assert params[0]['data'].startswith('0x70a08231')
    assert balance == Decimal('1.23')


def test_fetch_usdc_balance_on_bsc_respects_decimals():
    captured = {}

    def open_stub(req, timeout):
        body = json.loads(req.data.decode('utf-8'))
        captured['body'] = body
        return _dummy_rpc_response(hex(5 * 10**17))

    balance = fetch_usdc_balance_on_bsc(
        address='0xb794f5ea0ba39494ce839613fffba74279579268',
        api_key='key',
        opener=open_stub,
    )

    assert captured['body']['method'] == 'eth_call'
    assert captured['body']['params'][0]['to'].lower() == '0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d'
    assert balance == Decimal('0.5')


def test_fetch_eth_balance_on_ethereum_parses_rpc_response():
    class DummyResponse:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode('utf-8')

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def open_stub(req, timeout):
        body = json.loads(req.data.decode('utf-8'))
        assert body['method'] == 'eth_getBalance'
        assert body['params'][0] == '0xb794f5ea0ba39494ce839613fffba74279579268'
        return DummyResponse({'jsonrpc': '2.0', 'id': 1, 'result': hex(2 * 10**18)})

    balance = fetch_eth_balance_on_ethereum(
        address='0xb794f5ea0ba39494ce839613fffba74279579268',
        api_key='key',
        opener=open_stub,
    )
    assert balance == Decimal('2')


def test_fetch_usdt_balance_on_ethereum_uses_token_contract():
    captured = {}

    def open_stub(req, timeout):
        body = json.loads(req.data.decode('utf-8'))
        captured['body'] = body
        return _dummy_rpc_response(hex(1_230_000))

    balance = fetch_usdt_balance_on_ethereum(
        address='0xb794f5ea0ba39494ce839613fffba74279579268',
        api_key='key',
        opener=open_stub,
    )

    params = captured['body']['params']
    assert captured['body']['method'] == 'eth_call'
    assert params[0]['to'].lower() == '0xdac17f958d2ee523a2206206994597c13d831ec7'
    assert params[0]['data'].startswith('0x70a08231')
    assert balance == Decimal('1.23')


def test_fetch_usdc_balance_on_ethereum_respects_decimals():
    captured = {}

    def open_stub(req, timeout):
        body = json.loads(req.data.decode('utf-8'))
        captured['body'] = body
        return _dummy_rpc_response(hex(500_000))

    balance = fetch_usdc_balance_on_ethereum(
        address='0xb794f5ea0ba39494ce839613fffba74279579268',
        api_key='key',
        opener=open_stub,
    )

    assert captured['body']['method'] == 'eth_call'
    assert captured['body']['params'][0]['to'].lower() == '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'
    assert balance == Decimal('0.5')
