import pytest

from bot import *

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
]

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
