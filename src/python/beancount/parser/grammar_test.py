"""
Tests for grammar parser.
"""
__author__ = "Martin Blais <blais@furius.ca>"

import datetime
import unittest
import inspect
import textwrap
import re
from unittest import mock

from beancount.core.number import D
from beancount.core.number import ZERO
from beancount.core.amount import A
from beancount.parser import parser
from beancount.parser import lexer
from beancount.core import data
from beancount.core import amount
from beancount.core import position
from beancount.core import interpolate
from beancount.core import interpolate_test
from beancount.utils import test_utils
from beancount.parser import grammar
from beancount.parser import cmptest


def check_list(test, objlist, explist):
    """Assert the list of objects against the expected specification.

    Args:
      test: the instance of the test object, used for generating assertions.
      objlist: the list of objects returned.

      explist: the list of objects expected. 'explist' can be an integer, to
               check the length of the list; if it is a list of types, the types
               are checked against the types of the objects in the list. This is
               meant to be a convenient method.
    """
    if isinstance(explist, int):
        test.assertEqual(explist, len(objlist))
    elif isinstance(explist, (tuple, list)):
        test.assertEqual(len(explist), len(objlist))
        for obj, exp in zip(objlist, explist):
            test.assertTrue(isinstance(type(obj), type(exp)))


def raise_exception(*args, **kwargs):
    """Raises a ValueError exception.

    Args:
      *args: Callback arguments.
      *kwargs: Callback keyword arguments.
    Raises:
      ValueError: Unconditionally.
    """
    raise ValueError("Patched exception in parser")


class TestParserEntryTypes(unittest.TestCase):
    """Basic smoke test one entry of each kind."""

    @parser.parse_doc()
    def test_entry_transaction_1(self, entries, _, __):
        """
          2013-05-18 * "Nice dinner at Mermaid Inn"
            Expenses:Restaurant         100 USD
            Assets:US:Cash             -100 USD
        """
        check_list(self, entries, [data.Transaction])

    @parser.parse_doc()
    def test_entry_transaction_2(self, entries, _, __):
        """
          2013-05-18 txn "Nice dinner at Mermaid Inn"
            Expenses:Restaurant         100 USD
            Assets:US:Cash             -100 USD
        """
        check_list(self, entries, [data.Transaction])

    @parser.parse_doc()
    def test_entry_balance(self, entries, _, __):
        """
          option "experiment_explicit_tolerances" "TRUE"

          2013-05-18 balance Assets:US:BestBank:Checking  200 USD
          2013-05-18 balance Assets:US:BestBank:Checking  200 ~ 0.002 USD
        """
        check_list(self, entries, [data.Balance, data.Balance])

    @parser.parse_doc(expect_errors=True)
    def test_entry_balance_with_cost(self, entries, errors, __):
        """
          2013-05-18 balance Assets:Investments  10 MSFT {45.30 USD}
        """
        check_list(self, entries, [])
        check_list(self, errors, [parser.ParserSyntaxError])

    @parser.parse_doc()
    def test_entry_open_1(self, entries, _, __):
        """
          2013-05-18 open Assets:US:BestBank:Checking
        """
        check_list(self, entries, [data.Open])

    @parser.parse_doc()
    def test_entry_open_2(self, entries, _, __):
        """
          2013-05-18 open Assets:US:BestBank:Checking   USD
        """
        check_list(self, entries, [data.Open])

    @parser.parse_doc()
    def test_entry_open_3(self, entries, errors, __):
        """
          2013-05-18 open Assets:Cash   USD,CAD,EUR
        """
        check_list(self, entries, [data.Open])
        self.assertEqual(entries[0].booking, None)

    @parser.parse_doc()
    def test_entry_open_4(self, entries, errors, __):
        """
          2013-05-18 open Assets:US:Vanguard:VIIPX  VIIPX  "STRICT"
        """
        check_list(self, entries, [data.Open])
        self.assertEqual(entries[0].booking, 'STRICT')

    @parser.parse_doc()
    def test_entry_open_5(self, entries, errors, __):
        """
          2013-05-18 open Assets:US:Vanguard:VIIPX    "STRICT"
        """
        check_list(self, entries, [data.Open])
        self.assertEqual(entries[0].booking, 'STRICT')

    @parser.parse_doc()
    def test_entry_close(self, entries, _, __):
        """
          2013-05-18 close Assets:US:BestBank:Checking
        """
        check_list(self, entries, [data.Close])

    @parser.parse_doc()
    def test_entry_commodity(self, entries, _, __):
        """
          2013-05-18 commodity MSFT
        """
        check_list(self, entries, [data.Commodity])

    @parser.parse_doc()
    def test_entry_pad(self, entries, _, __):
        """
          2013-05-18 pad Assets:US:BestBank:Checking  Equity:Opening-Balances
        """
        check_list(self, entries, [data.Pad])

    @parser.parse_doc()
    def test_entry_event(self, entries, _, __):
        """
          2013-05-18 event "location" "New York, USA"
        """
        check_list(self, entries, [data.Event])

    @parser.parse_doc()
    def test_entry_query(self, entries, _, __):
        """
          option "experiment_query_directive" "TRUE"
          2013-05-18 query "cash" "SELECT SUM(position) WHERE currency = 'USD'"
        """
        check_list(self, entries, [data.Query])

    @parser.parse_doc(expect_errors=True)
    def test_entry_query__not_enabled(self, entries, errors, __):
        """
          2013-05-18 query "cash" "SELECT SUM(position) WHERE currency = 'USD'"
        """
        self.assertRegexpMatches(errors[0].message, "Query directive is not supported")
        self.assertEqual([], entries)

    @parser.parse_doc()
    def test_entry_note(self, entries, _, __):
        """
          2013-05-18 note Assets:US:BestBank:Checking  "Blah, di blah."
        """
        check_list(self, entries, [data.Note])

    @parser.parse_doc()
    def test_entry_price(self, entries, _, __):
        """
          2013-05-18 price USD   1.0290 CAD
        """
        check_list(self, entries, [data.Price])


class TestParserComplete(unittest.TestCase):
    """Tests of completion of balance."""

    @parser.parse_doc()
    def test_entry_transaction_single_posting_at_zero(self, entries, errors, _):
        """
          2013-05-18 * "Nice dinner at Mermaid Inn"
            Expenses:Restaurant         0 USD
        """
        check_list(self, entries, [data.Transaction])
        check_list(self, errors, 0)

    @parser.parse_doc()
    def test_entry_transaction_imbalance_from_single_posting(self, entries, errors, _):
        """
          2013-05-18 * "Nice dinner at Mermaid Inn"
            Expenses:Restaurant         100 USD
        """
        check_list(self, entries, [data.Transaction])
        check_list(self, errors, 1 if interpolate_test.ERRORS_ON_RESIDUAL else 0)
        entry = entries[0]
        self.assertEqual(1, len(entry.postings))


class TestUglyBugs(unittest.TestCase):
    """Test all kinds of stupid sh*t that will inevitably occur in practice."""

    @parser.parse_doc()
    def test_empty_1(self, entries, errors, _):
        ""
        check_list(self, entries, [])
        check_list(self, errors, [])

    @parser.parse_doc()
    def test_empty_2(self, entries, errors, _):
        """

        """
        check_list(self, entries, [])
        check_list(self, errors, [])

    @parser.parse_doc()
    def test_comment(self, entries, errors, _):
        """
        ;; This is some comment.
        """
        check_list(self, entries, [])
        check_list(self, errors, [])

    def test_extra_whitespace_note(self):
        input_ = '\n2013-07-11 note Assets:Cash "test"\n\n  ;;\n'
        entries, errors, _ = parser.parse_string(input_)
        check_list(self, entries, [data.Note])
        check_list(self, errors, [])

    def test_extra_whitespace_transaction(self):
        input_ = '\n'.join([
            '2013-05-18 * "Nice dinner at Mermaid Inn"',
            '  Expenses:Restaurant         100 USD',
            '  Assets:US:Cash',
            '  ',
            ';; End of file',
        ])

        entries, errors, _ = parser.parse_string(input_, yydebug=0)
        check_list(self, entries, [data.Transaction])
        check_list(self, errors, [])

    def test_extra_whitespace_comment(self):
        input_ = '\n'.join([
            '2013-05-18 * "Nice dinner at Mermaid Inn"',
            '  Expenses:Restaurant         100 USD',
            '  Assets:US:Cash',
            '  ;;',
        ])
        entries, errors, _ = parser.parse_string(input_)
        check_list(self, entries, [data.Transaction])
        check_list(self, errors, [])

    @parser.parse_doc()
    def test_indent_eof(self, entries, errors, _):
        "\t"
        check_list(self, entries, [])
        check_list(self, errors, [])

    @parser.parse_doc()
    def test_comment_eof(self, entries, errors, _):
        "; comment"
        check_list(self, entries, [])
        check_list(self, errors, [])

    @parser.parse_doc()
    def test_no_empty_lines(self, entries, errors, _):
        """
          2013-05-01 open Assets:Cash   USD,CAD,EUR
          2013-05-02 close Assets:US:BestBank:Checking
          2013-05-03 pad Assets:US:BestBank:Checking  Equity:Opening-Balancess
          2013-05-04 event "location" "New York, USA"
          2013-05-05 * "Payee" "Narration"
            Assets:US:BestBank:Checking   100.00 USD
            Assets:Cash                  -100.00 USD
          2013-05-06 note Assets:US:BestBank:Checking  "Blah, di blah."
          2013-05-07 price USD   1.0290 CAD
        """
        self.assertEqual(7, len(entries))
        self.assertEqual([], errors)


class TestTagStack(unittest.TestCase):

    @parser.parse_doc(expect_errors=True)
    def test_tag_left_unclosed(self, entries, errors, _):
        """
          pushtag #trip-to-nowhere
        """
        self.assertEqual(1, len(errors))
        self.assertTrue(re.search('Unbalanced tag', errors[0].message))

    @parser.parse_doc(expect_errors=True)
    def test_pop_invalid_tag(self, entries, errors, _):
        """
          poptag #trip-to-nowhere
        """
        self.assertTrue(errors)
        self.assertTrue(re.search('absent tag', errors[0].message))


class TestMultipleLines(unittest.TestCase):

    @parser.parse_doc()
    def test_multiline_narration(self, entries, errors, _):
        """
          2014-07-11 * "Hello one line
          and yet another,
          and why not another!"
            Expenses:Restaurant         100 USD
            Assets:Cash                -100 USD
        """
        self.assertEqual(1, len(entries))
        self.assertFalse(errors)
        self.assertFalse(lexer.LexerError in map(type, errors))
        expected_narration = "Hello one line\nand yet another,\nand why not another!"
        self.assertEqual(expected_narration, entries[0].narration)


class TestSyntaxErrors(unittest.TestCase):
    """Test syntax errors that occur within the parser.
    One of our goals is to recover and report without ever
    bailing out with an exception."""

    @parser.parse_doc(expect_errors=True)
    def test_lexer_default_rule_1(self, entries, errors, _):
        """
          Account:*:Bla
        """
        self.assertEqual(entries, [])
        self.assertTrue(errors)
        self.assertTrue(lexer.LexerError in map(type, errors))

    @parser.parse_doc(expect_errors=True)
    def test_lexer_default_rule_2(self, entries, errors, _):
        """
          2013-05-18 * "Nice dinner at Mermaid Inn"
            Expenses:Resta(urant        100 USD
            Expenses:Tips                10 USD
            Assets:US:Cash             -110 USD

          2013-05-20 balance Assets:US:Cash  -110 USD
        """
        # This should fail to parse the "Expenses:Resta(urant" account name.

        # Check that we indeed read the 'check' entry that comes after the one
        # with the error.
        check_list(self, entries, [data.Balance])

        # Make sure at least one error is reported.
        self.assertEqual(1, len(errors))
        self.assertIsInstance(errors[0], lexer.LexerError)
        self.assertRegexpMatches(errors[0].message, 'Invalid token')

    @parser.parse_doc()
    def test_no_final_newline(self, entries, errors, _):
        """
          2014-11-02 *
            Assets:Something   1 USD
            Assets:Other      -1 USD"""
        self.assertFalse(errors)
        self.assertEqual(1, len(entries))
        self.assertEqual(2, len(entries[0].postings))


class TestLineNumbers(unittest.TestCase):
    """Check that the line numbers line up correctly."""

    @parser.parse_doc()
    def test_line_numbers(self, entries, errors, _):
        """
          2013-05-18 * "Nice dinner at Mermaid Inn"
            Expenses:Restaurant         100 USD
            Assets:US:Cash             -100 USD

          2013-05-19 balance  Assets:US:Cash   -100 USD

          2013-05-20 note  Assets:US:Cash   "Something"

        """
        _, first_line = inspect.getsourcelines(
            TestLineNumbers.test_line_numbers.__wrapped__)
        first_line += 1

        self.assertEqual(2, entries[0].meta["lineno"] - first_line)
        self.assertEqual(6, entries[1].meta["lineno"] - first_line)
        self.assertEqual(8, entries[2].meta["lineno"] - first_line)


class TestParserOptions(unittest.TestCase):

    @parser.parse_doc()
    def test_option_single_value(self, entries, errors, options_map):
        """
          option "title" "Super Rich"

        """
        option = options_map['title']
        self.assertEqual(option, 'Super Rich')

    @parser.parse_doc()
    def test_option_list_value(self, entries, errors, options_map):
        """
          option "documents" "/path/docs/a"
          option "documents" "/path/docs/b"
          option "documents" "/path/docs/c"

        """
        documents = options_map['documents']
        self.assertEqual(['/path/docs/a',
                          '/path/docs/b',
                          '/path/docs/c'], documents)

    @parser.parse_doc(expect_errors=True)
    def test_invalid_option(self, entries, errors, options_map):
        """
          option "bladibla_invalid" "Some value"

        """
        check_list(self, errors, [parser.ParserError])
        self.assertFalse("bladibla_invalid" in options_map)

    @parser.parse_doc(expect_errors=True)
    def test_readonly_option(self, entries, errors, options_map):
        """
          option "filename" "gniagniagniagniagnia"

        """
        check_list(self, errors, [parser.ParserError])
        self.assertNotEqual("filename", "gniagniagniagniagnia")


class TestParserInclude(unittest.TestCase):

    def test_parse_nonexist(self):
        with self.assertRaises(OSError):
            parser.parse_file('/some/bullshit/filename.beancount')

    @test_utils.docfile
    def test_include_absolute(self, filename):
        """
          include "/some/absolute/filename.beancount"
        """
        entries, errors, options_map = parser.parse_file(filename)
        self.assertFalse(errors)
        self.assertEqual(['/some/absolute/filename.beancount'],
                         options_map['include'])

    @test_utils.docfile
    def test_include_relative(self, filename):
        """
          include "some/relative/filename.beancount"
        """
        entries, errors, options_map = parser.parse_file(filename)
        self.assertFalse(errors)
        self.assertEqual(['some/relative/filename.beancount'],
                         options_map['include'])

    def test_include_relative_from_string(self):
        input_string = """
          include "some/relative/filename.beancount"
        """
        entries, errors, options_map = parser.parse_string(input_string)
        self.assertFalse(errors)
        self.assertEqual(['some/relative/filename.beancount'],
                         options_map['include'])


class TestParserPlugin(unittest.TestCase):

    @parser.parse_doc()
    def test_plugin(self, entries, errors, options_map):
        """
          plugin "beancount.plugin.unrealized"
        """
        self.assertFalse(errors)
        self.assertEqual([('beancount.plugin.unrealized', None)],
                         options_map['plugin'])

    @parser.parse_doc()
    def test_plugin_with_config(self, entries, errors, options_map):
        """
          plugin "beancount.plugin.unrealized" "Unrealized"
        """
        self.assertFalse(errors)
        self.assertEqual([('beancount.plugin.unrealized', 'Unrealized')],
                         options_map['plugin'])

    # Note: this is testing the old method, which will become obsolete one day.
    @parser.parse_doc(expect_errors=True)
    def test_plugin_as_option(self, entries, errors, options_map):
        """
          option "plugin" "beancount.plugin.unrealized"
        """
        self.assertEqual(1, len(errors))
        self.assertEqual([('beancount.plugin.unrealized', None)],
                         options_map['plugin'])

    @parser.parse_doc(expect_errors=True)
    def test_plugin_as_option_with_config(self, entries, errors, options_map):
        """
          option "plugin" "beancount.plugin.unrealized:Unrealized"
        """
        self.assertEqual(1, len(errors))
        self.assertEqual([('beancount.plugin.unrealized', 'Unrealized')],
                         options_map['plugin'])


class TestDisplayContextOptions(unittest.TestCase):

    @parser.parse_doc()
    def test_render_commas_no(self, _, __, options_map):
        """
          option "render_commas" "0"
        """
        self.assertEqual(False, options_map['render_commas'])

    @parser.parse_doc()
    def test_render_commas_yes(self, _, __, options_map):
        """
          option "render_commas" "1"
        """
        self.assertEqual(True, options_map['render_commas'])

    @parser.parse_doc()
    def test_render_commas_yes2(self, _, __, options_map):
        """
          option "render_commas" "TRUE"
        """
        self.assertEqual(True, options_map['render_commas'])


class TestMiscOptions(unittest.TestCase):

    @parser.parse_doc(expect_errors=False)
    def test_plugin_processing_mode__default(self, _, __, options_map):
        """
        option "plugin_processing_mode" "default"
        """
        self.assertEqual("default", options_map['plugin_processing_mode'])

    @parser.parse_doc(expect_errors=False)
    def test_plugin_processing_mode__raw(self, _, __, options_map):
        """
        option "plugin_processing_mode" "raw"
        """
        self.assertEqual("raw", options_map['plugin_processing_mode'])

    @parser.parse_doc(expect_errors=True)
    def test_plugin_processing_mode__invalid(self, _, errors, options_map):
        """
        option "plugin_processing_mode" "invalid"
        """
        self.assertEqual(1, len(errors))
        self.assertTrue(re.match("Error for option", errors[0].message))
        self.assertEqual("default", options_map['plugin_processing_mode'])

    @parser.parse_doc(expect_errors=True)
    def test_account_rounding_old_fixup(self, _, errors, options_map):
        """
        option "account_rounding" "Equity:RoundingError"
        """
        self.assertEqual(1, len(errors))
        self.assertRegexpMatches(errors[0].message, "should now refer to.*subaccount")
        self.assertEqual(options_map['account_rounding'], 'RoundingError')


class TestToleranceOptions(unittest.TestCase):

    @parser.parse_doc()
    def test_tolerance_defaults(self, _, __, options_map):
        """
        """
        self.assertEqual(D('0.015'),
                         options_map['tolerance'])
        self.assertEqual({},
                         options_map['default_tolerance'])

    @parser.parse_doc(expect_errors=True)
    def test_tolerance__deprecated(self, _, errors, options_map):
        """
          option "tolerance" "0.05"
        """
        self.assertEqual(D("0.05"), options_map['tolerance'])
        self.assertRegexpMatches(errors[0].message, "has been deprecated")

    @parser.parse_doc()
    def test_default_tolerance(self, _, __, options_map):
        """
          option "default_tolerance" "*:0"
          option "default_tolerance" "USD:0.05"
          option "default_tolerance" "JPY:0.5"
        """
        self.assertEqual({"*": D("0"),
                          "USD": D("0.05"),
                          "JPY": D("0.5")},
                         options_map['default_tolerance'])


class TestDeprecatedOptions(unittest.TestCase):

    @parser.parse_doc(expect_errors=True)
    def test_deprecated_plugin(self, _, errors, __):
        """
          option "plugin" "beancount.plugins.module_name"
        """
        self.assertEqual(1, len(errors))
        self.assertTrue(re.search('option is deprecated', errors[0].message))

    @parser.parse_doc(expect_errors=True)
    def test_deprecated_tolerance(self, _, errors, __):
        """
          option "tolerance" "0.00005"
        """
        self.assertEqual(1, len(errors))
        self.assertTrue(re.search('option has been deprecated', errors[0].message))


class TestParserLinks(unittest.TestCase):

    @parser.parse_doc()
    def test_links(self, entries, errors, _):
        """
          2013-05-18 * "Something something" ^38784734873
            Expenses:Restaurant         100 USD
            Assets:US:Cash             -100 USD

        """
        check_list(self, entries, [data.Transaction])
        self.assertEqual(entries[0].links, set(['38784734873']))


class TestTransactions(unittest.TestCase):

    @parser.parse_doc()
    def test_simple_1(self, entries, errors, _):
        """
          2013-05-18 * "Nice dinner at Mermaid Inn"
            Expenses:Restaurant         100 USD
            Assets:US:Cash             -100 USD
        """
        check_list(self, entries, [data.Transaction])
        check_list(self, errors, [])
        self.assertEqual(None, entries[0].payee)
        self.assertEqual("Nice dinner at Mermaid Inn", entries[0].narration)

    @parser.parse_doc()
    def test_simple_2(self, entries, errors, _):
        """

          2013-05-18 * "Nice dinner at Mermaid Inn"
            Expenses:Restaurant         100 USD
            Assets:US:Cash             -100 USD

          2013-05-20 * "Duane Reade" | "Toothbrush"
            Expenses:BathroomSupplies         4 USD
            Assets:US:BestBank:Checking      -4 USD

        """
        check_list(self, entries, [data.Transaction, data.Transaction])
        check_list(self, errors, [])
        self.assertEqual(None, entries[0].payee)
        self.assertEqual("Nice dinner at Mermaid Inn", entries[0].narration)
        self.assertEqual("Duane Reade", entries[1].payee)
        self.assertEqual("Toothbrush", entries[1].narration)

    @parser.parse_doc()
    def test_empty_narration(self, entries, errors, _):
        """
          2013-05-18 * ""
            Expenses:Restaurant         100 USD
            Assets:US:Cash             -100 USD
        """
        check_list(self, entries, [data.Transaction])
        check_list(self, errors, [])
        self.assertEqual("", entries[0].narration)
        self.assertEqual(None, entries[0].payee)

    @parser.parse_doc()
    def test_no_narration(self, entries, errors, _):
        """
          2013-05-18 *
            Expenses:Restaurant         100 USD
            Assets:US:Cash             -100 USD
        """
        check_list(self, entries, [data.Transaction])
        check_list(self, errors, [])
        self.assertEqual("", entries[0].narration)
        self.assertEqual(None, entries[0].payee)

    @parser.parse_doc(expect_errors=True)
    def test_payee_no_narration(self, entries, errors, _):
        """
          2013-05-18 * "Mermaid Inn" |
            Expenses:Restaurant         100 USD
            Assets:US:Cash             -100 USD
        """
        # Make sure a single string and a pipe raises an error, because '|' does
        # not carry any special meaning anymore.
        check_list(self, entries, [data.Transaction])
        check_list(self, errors, [parser.ParserError])
        self.assertEqual(None, entries[0].payee)
        self.assertEqual("Mermaid Inn", entries[0].narration)

    @parser.parse_doc(expect_errors=True)
    def test_too_many_strings(self, entries, errors, _):
        """
          2013-05-18 * "A" "B" "C"
            Expenses:Restaurant         100 USD
            Assets:US:Cash             -100 USD
        """
        check_list(self, entries, [])
        check_list(self, errors, [parser.ParserError])

    @parser.parse_doc()
    def test_link_and_then_tag(self, entries, errors, _):
        """
          2014-04-20 * "Money from CC" ^610fa7f17e7a #trip
            Expenses:Restaurant         100 USD
            Assets:US:Cash             -100 USD
        """
        check_list(self, entries, [data.Transaction])
        check_list(self, errors, [])
        self.assertEqual("Money from CC", entries[0].narration)
        self.assertEqual(None, entries[0].payee)
        self.assertEqual(set(["610fa7f17e7a"]), entries[0].links)
        self.assertEqual(set(["trip"]), entries[0].tags)

    @parser.parse_doc()
    def test_tag_then_link(self, entries, errors, _):
        """
          2014-04-20 * #trip "Money from CC" ^610fa7f17e7a
            Expenses:Restaurant         100 USD
            Assets:US:Cash             -100 USD
        """
        check_list(self, entries, [data.Transaction])
        check_list(self, errors, [])
        self.assertEqual("Money from CC", entries[0].narration)
        self.assertEqual(None, entries[0].payee)
        self.assertEqual(set(["610fa7f17e7a"]), entries[0].links)
        self.assertEqual(set(["trip"]), entries[0].tags)

    @parser.parse_doc()
    def test_zero_prices(self, entries, errors, _):
        """
          2014-04-20 * "Like a conversion entry"
            Equity:Conversions         100 USD @ 0 XFER
            Equity:Conversions         101 CAD @ 0 XFER
            Equity:Conversions         102 AUD @ 0 XFER
        """
        check_list(self, entries, [data.Transaction])
        check_list(self, errors, [])

    @parser.parse_doc(expect_errors=False)
    def test_zero_units(self, entries, errors, _):
        """
          2014-04-20 * "Zero number of units"
            Assets:Investment         0 HOOL {500.00 USD}
            Assets:Cash               0 USD
        """
        check_list(self, entries, [data.Transaction])
        # Note: Zero amount is caught only at booking time.
        self.assertFalse(errors)

    @parser.parse_doc()
    def test_zero_costs(self, entries, errors, _):
        """
          2014-04-20 * "Like a conversion entry"
            Assets:Investment         10 HOOL {0 USD}
            Assets:Cash                0 USD
        """
        check_list(self, entries, [data.Transaction])
        check_list(self, errors, [])

    @parser.parse_doc()
    def test_imbalance(self, entries, errors, _):
        """
          2014-04-20 * "Busted!"
            Assets:Checking         100 USD
            Assets:Checking         -99 USD
        """
        check_list(self, entries, [data.Transaction])
        check_list(self, errors,
                   [interpolate.BalanceError]
                   if interpolate_test.ERRORS_ON_RESIDUAL else [])

    @parser.parse_doc()
    def test_no_postings(self, entries, errors, _):
        """
          2014-07-17 * "(JRN) INTRA-ACCOUNT TRANSFER" ^795422780
        """
        self.assertTrue(isinstance(entries[0].postings, list))


class TestParseLots(unittest.TestCase):

    maxDiff = None

    @parser.parse_doc()
    def test_lot_nolot(self, entries, errors, _):
        """
          2014-01-01 *
            Assets:Invest:AAPL   45.23 USD
            Assets:Invest:Cash  -45.23 USD
        """
        self.assertFalse(errors)
        pos = entries[0].postings[0].position
        self.assertEqual(D('45.23'), pos.number)
        self.assertEqual(grammar.LotSpec('USD', None, None, None, None), pos.lot)

    @parser.parse_doc()
    def test_lot_empty(self, entries, errors, _):
        """
          2014-01-01 *
            Assets:Invest:AAPL   20 AAPL {}
            Assets:Invest:Cash  -20 AAPL
        """
        self.assertFalse(errors)
        pos = entries[0].postings[0].position
        self.assertEqual(D('20'), pos.number)
        self.assertEqual(grammar.LotSpec('AAPL', None, None, None, None), pos.lot)

    @parser.parse_doc()
    def test_lot_cost(self, entries, errors, _):
        """
          2014-01-01 *
            Assets:Invest:AAPL      20 AAPL {45.23 USD}
            Assets:Invest:Cash  -90.46 USD
        """
        self.assertFalse(errors)
        pos = entries[0].postings[0].position
        self.assertEqual(D('20'), pos.number)
        self.assertEqual(
            position.LotSpec('AAPL',
                             grammar.CompoundAmount(D('45.23'), None, 'USD'),
                             None, None, None),
                         pos.lot)

    @parser.parse_doc()
    def test_lot_date(self, entries, errors, _):
        """
          2014-01-01 *
            Assets:Invest:AAPL   20 AAPL {2014-12-26}
            Assets:Invest:Cash  -20 AAPL
        """
        self.assertFalse(errors)
        pos = entries[0].postings[0].position
        self.assertEqual(D('20'), pos.number)
        self.assertEqual(
            grammar.LotSpec('AAPL', None, datetime.date(2014, 12, 26), None, None),
            pos.lot)

    @parser.parse_doc(expect_errors=True)
    def test_lot_label(self, entries, errors, _):
        """
          2014-01-01 *
            Assets:Invest:AAPL   20 AAPL {"d82d55a0dbe8"}
            Assets:Invest:Cash  -20 AAPL
        """
        self.assertEqual(1, len(errors))
        self.assertTrue(re.search("Labels not supported", errors[0].message))
        pos = entries[0].postings[0].position
        self.assertEqual(D('20'), pos.number)
        self.assertEqual(grammar.LotSpec('AAPL', None, None, "d82d55a0dbe8", None), pos.lot)

    @parser.parse_doc(expect_errors=True)
    def test_lot_merge(self, entries, errors, _):
        """
          2014-01-01 *
            Assets:Invest:AAPL   20 AAPL {*}
            Assets:Invest:Cash  -20 AAPL
        """
        self.assertEqual(1, len(errors))
        self.assertTrue(re.search("Merge-cost not supported", errors[0].message))
        pos = entries[0].postings[0].position
        self.assertEqual(D('20'), pos.number)
        self.assertEqual(grammar.LotSpec('AAPL', None, None, None, True), pos.lot)

    @parser.parse_doc(expect_errors=True)
    def test_lot_two_types(self, entries, errors, _):
        """
          2014-01-01 *
            Assets:Invest:AAPL    1 AAPL {45.23 USD, 2014-12-26}
            Assets:Invest:AAPL    1 AAPL {2014-12-26, 45.23 USD}
            Assets:Invest:AAPL    1 AAPL {45.23 USD, "d82d55a0dbe8"}
            Assets:Invest:AAPL    1 AAPL {"d82d55a0dbe8", 45.23 USD}
            Assets:Invest:AAPL    1 AAPL {2014-12-26, "d82d55a0dbe8"}
            Assets:Invest:AAPL    1 AAPL {"d82d55a0dbe8", 2014-12-26}
        """
        self.assertEqual(4, len(errors))
        self.assertTrue(all(re.search("Labels not supported", error.message)
                            for error in errors))

    @parser.parse_doc(expect_errors=True)
    def test_lot_three_types(self, entries, errors, _):
        """
          2014-01-01 *
            Assets:Invest:AAPL    1 AAPL {45.23 USD, 2014-12-26, "d82d55a0dbe8"}
            Assets:Invest:AAPL    1 AAPL {2014-12-26, 45.23 USD, "d82d55a0dbe8"}
            Assets:Invest:AAPL    1 AAPL {45.23 USD, "d82d55a0dbe8", 2014-12-26}
            Assets:Invest:AAPL    1 AAPL {2014-12-26, "d82d55a0dbe8", 45.23 USD}
            Assets:Invest:AAPL    1 AAPL {"d82d55a0dbe8", 45.23 USD, 2014-12-26}
            Assets:Invest:AAPL    1 AAPL {"d82d55a0dbe8", 2014-12-26, 45.23 USD}
        """
        self.assertEqual(6, len(errors))
        self.assertTrue(all(re.search("Labels not supported", error.message)
                            for error in errors))

    @parser.parse_doc(expect_errors=True)
    def test_lot_repeated_cost(self, entries, errors, _):
        """
          2014-01-01 *
            Assets:Invest:AAPL       1 AAPL {45.23 USD, 45.24 USD}
            Assets:Invest:Cash  -45.23 USD
        """
        self.assertEqual(1, len(errors))
        self.assertTrue(re.search("Duplicate cost", errors[0].message))

    @parser.parse_doc(expect_errors=True)
    def test_lot_repeated_date(self, entries, errors, _):
        """
          2014-01-01 *
            Assets:Invest:AAPL    1 AAPL {45.23 USD, 2014-12-26, 2014-12-27}
            Assets:Invest:Cash   -1 AAPL
        """
        self.assertEqual(1, len(errors))
        self.assertTrue(re.search("Duplicate date", errors[0].message))

    @parser.parse_doc(expect_errors=True)
    def test_lot_repeated_label(self, entries, errors, _):
        """
          2014-01-01 *
            Assets:Invest:AAPL       1 AAPL {"aaa", "bbb", 45.23 USD}
            Assets:Invest:Cash  -45.23 USD
        """
        self.assertEqual(2, len(errors))
        self.assertTrue(any(re.search("Duplicate label", error.message)
                            for error in errors))
        self.assertTrue(any(re.search("Labels not supported", error.message)
                            for error in errors))

    @parser.parse_doc(expect_errors=True)
    def test_lot_repeated_merge(self, entries, errors, _):
        """
          2014-01-01 *
            Assets:Invest:AAPL       1 AAPL {*, *}
            Assets:Invest:Cash  -45.23 USD
        """
        self.assertEqual(2, len(errors))
        self.assertTrue(any(re.search("Duplicate merge", error.message)
                            for error in errors))
        self.assertTrue(any(re.search("Merge-cost not supported", error.message)
                            for error in errors))

    @parser.parse_doc()
    def test_lot_both_costs(self, entries, errors, _):
        """
          2014-01-01 *
            Assets:Invest:AAPL       10 AAPL {45.23 # 9.95 USD}
            Assets:Invest:Cash  -110.36 USD
        """
        pos = entries[0].postings[0].position
        self.assertEqual(grammar.CompoundAmount(D('45.23'), D('9.95'), 'USD'),
                         pos.lot.compound_cost)

    @parser.parse_doc()
    def test_lot_total_cost_only(self, entries, errors, _):
        """
          2014-01-01 *
            Assets:Invest:AAPL      10 AAPL {# 9.95 USD}
            Assets:Invest:Cash  -19.90 USD
        """
        pos = entries[0].postings[0].position
        self.assertEqual(grammar.CompoundAmount(None, D('9.95'), 'USD'),
                         pos.lot.compound_cost)

    @parser.parse_doc()
    def test_lot_total_empty_total(self, entries, errors, _):
        """
          2014-01-01 *
            Assets:Invest:AAPL      20 AAPL {45.23 # USD}
            Assets:Invest:Cash  -45.23 USD
        """
        self.assertEqual(0, len(errors))
        pos = entries[0].postings[0].position
        self.assertEqual(D('20'), pos.number)
        self.assertEqual(
            position.LotSpec('AAPL',
                             grammar.CompoundAmount(D('45.23'), None, 'USD'),
                             None, None, None),
            pos.lot)

    @parser.parse_doc()
    def test_lot_total_just_currency(self, entries, errors, _):
        """
          2014-01-01 *
            Assets:Invest:AAPL   20 AAPL {USD}
            Assets:Invest:AAPL   20 AAPL { # USD}
            Assets:Invest:Cash    0 USD
        """

    @parser.parse_doc(expect_errors=True)
    def test_lot_with_slashes(self, entries, errors, _):
        """
          2014-01-01 *
            Assets:Invest:AAPL      1.1 AAPL {45.23 USD / 2015-07-16 / "blabla"}
            Assets:Invest:Cash   -45.23 USD
        """
        # Note: When marking SLASH as deprecated, bring this check back in.
        # {a6127ff32048}
        # self.assertEqual(3, len(errors))
        # self.assertTrue(re.search("slash", errors[0].message))
        # self.assertTrue(re.search("slash", errors[1].message))
        self.assertEqual(1, len(errors))
        self.assertTrue(re.search("Labels not supported", errors[0].message))
        pos = entries[0].postings[0].position
        self.assertEqual(D('1.1'), pos.number)
        self.assertEqual(position.LotSpec('AAPL',
                                          grammar.CompoundAmount(D('45.23'), None, 'USD'),
                                          datetime.date(2015, 7, 16),
                                          'blabla',
                                          None),
                         pos.lot)


class TestCurrencies(unittest.TestCase):

    @parser.parse_doc()
    def test_parse_currencies(self, entries, errors, _):
        """
          2014-01-19 open Assets:Underscore    DJ_EURO
          2014-01-19 open Assets:Period        DJ.EURO
          2014-01-19 open Assets:Apostrophe    DJ'EURO
          2014-01-19 open Assets:Numbers       EURO123
        """
        self.assertFalse(errors)


class TestTotalsAndSigns(unittest.TestCase):

    @parser.parse_doc(expect_errors=False)
    def test_zero_amount(self, entries, errors, _):
        """
          2013-05-18 * ""
            Assets:Investments:MSFT      0 MSFT {200.00 USD}
            Assets:Investments:Cash      0 USD
        """
        pass # Should produce no errors.

    @parser.parse_doc(expect_errors=False)
    def test_zero_cost(self, entries, errors, _):
        """
          2013-05-18 * ""
            Assets:Investments:MSFT      -10 MSFT {0.00 USD}
            Assets:Investments:Cash     0.00 USD
        """
        pass # Should produce no errors.

    @parser.parse_doc(expect_errors=False)
    def test_cost_negative(self, entries, errors, _):
        """
          2013-05-18 * ""
            Assets:Investments:MSFT      -10 MSFT {-200.00 USD}
            Assets:Investments:Cash  2000.00 USD
        """
        pass # Should produce no errors.
        # Note: This error is caught only at booking time.

    @parser.parse_doc()
    def test_total_cost(self, entries, errors, _):
        """
          2013-05-18 * ""
            Assets:Investments:MSFT      10 MSFT {{2,000 USD}}
            Assets:Investments:Cash  -20000 USD

          2013-05-18 * ""
            Assets:Investments:MSFT      10 MSFT {{2000 USD / 2014-02-25}}
            Assets:Investments:Cash  -20000 USD

          2013-06-01 * ""
            Assets:Investments:MSFT      -10 MSFT {{2,000 USD}}
            Assets:Investments:Cash    20000 USD
        """
        for entry in entries:
            posting = entry.postings[0]
            self.assertEqual(grammar.CompoundAmount(ZERO, D('2000'), 'USD'),
                             posting.position.lot.compound_cost)
            self.assertEqual(None, posting.price)

    @parser.parse_doc(expect_errors=False)
    def test_total_cost_negative(self, entries, errors, _):
        """
          2013-05-18 * ""
            Assets:Investments:MSFT      -10 MSFT {{-200.00 USD}}
            Assets:Investments:Cash   200.00 USD
        """
        pass # Should produce no errors.
        # Note: This error is caught only at booking time.

    @parser.parse_doc(expect_errors=True)
    def test_price_negative(self, entries, errors, _):
        """
          2013-05-18 * ""
            Assets:Investments:MSFT      -10 MSFT @ -200.00 USD
            Assets:Investments:Cash  2000.00 USD
        """
        self.assertTrue(re.search('Negative.*allowed', errors[0].message))

    @parser.parse_doc()
    def test_total_price_positive(self, entries, errors, _):
        """
          2013-05-18 * ""
            Assets:Investments:MSFT        10 MSFT @@ 2000.00 USD
            Assets:Investments:Cash  -2000.00 USD
        """
        posting = entries[0].postings[0]
        self.assertEqual(A('200 USD'), posting.price)
        self.assertEqual(None, posting.position.lot.compound_cost)

    @parser.parse_doc()
    def test_total_price_negative(self, entries, errors, _):
        """
          2013-05-18 * ""
            Assets:Investments:MSFT       -10 MSFT @@ 2000.00 USD
            Assets:Investments:Cash  20000.00 USD
        """
        posting = entries[0].postings[0]
        self.assertEqual(A('200 USD'), posting.price)
        self.assertEqual(None, posting.position.lot.compound_cost)

    @parser.parse_doc(expect_errors=True)
    def test_total_price_inverted(self, entries, errors, _):
        """
          2013-05-18 * ""
            Assets:Investments:MSFT         10 MSFT @@ -2000.00 USD
            Assets:Investments:Cash   20000.00 USD
        """
        self.assertTrue(re.search('Negative.*allowed', errors[0].message))


class TestAllowNegativePrices(unittest.TestCase):

    def setUp(self):
        self.__allow_negative_prices__ = grammar.__allow_negative_prices__
        grammar.__allow_negative_prices__ = True

    def tearDown(self):
        grammar.__allow_negative_prices__ = self.__allow_negative_prices__

    @parser.parse_doc()
    def test_total_cost(self, entries, errors, _):
        """
          2013-05-18 * ""
            Assets:Investments:MSFT      10 MSFT {{2,000 USD}}
            Assets:Investments:Cash  -20000 USD

          2013-05-18 * ""
            Assets:Investments:MSFT      10 MSFT {{2000 USD / 2014-02-25}}
            Assets:Investments:Cash  -20000 USD

          2013-06-01 * ""
            Assets:Investments:MSFT      -10 MSFT {{2,000 USD}}
            Assets:Investments:Cash    20000 USD
        """
        self.assertFalse(errors)
        for entry in entries:
            posting = entry.postings[0]
            self.assertEqual(grammar.CompoundAmount(ZERO, D('2000'), 'USD'),
                             posting.position.lot.compound_cost)
            self.assertEqual(None, posting.price)

    @parser.parse_doc()
    def test_price_negative(self, entries, errors, _):
        """
          2013-05-18 * ""
            Assets:Investments:MSFT      -10 MSFT @ -200.00 USD
            Assets:Investments:Cash  2000.00 USD
        """
        posting = entries[0].postings[0]
        self.assertEqual(A('-200 USD'), posting.price)
        self.assertEqual(None, posting.position.lot.compound_cost)

    @parser.parse_doc()
    def test_total_price_negative(self, entries, errors, _):
        """
          2013-05-18 * ""
            Assets:Investments:MSFT        -10 MSFT @@ 2000.00 USD
            Assets:Investments:Cash   20000.00 USD
        """
        posting = entries[0].postings[0]
        self.assertEqual(A('-200 USD'), posting.price)
        self.assertEqual(None, posting.position.lot.compound_cost)

    @parser.parse_doc()
    def test_total_price_inverted(self, entries, errors, _):
        """
          2013-05-18 * ""
            Assets:Investments:MSFT         10 MSFT @@ -2000.00 USD
            Assets:Investments:Cash  -20000.00 USD
        """
        posting = entries[0].postings[0]
        self.assertEqual(A('-200 USD'), posting.price)
        self.assertEqual(None, posting.position.lot.compound_cost)


class TestBalance(unittest.TestCase):

    @parser.parse_doc()
    def test_total_price(self, entries, errors, _):
        """
          2013-05-18 * ""
            Assets:Investments:MSFT      10 MSFT @@ 2000 USD
            Assets:Investments:Cash  -20000 USD
        """
        posting = entries[0].postings[0]
        self.assertEqual(A('200 USD'), posting.price)
        self.assertEqual(None, posting.position.lot.compound_cost)

    @parser.parse_doc()
    def test_total_cost(self, entries, errors, _):
        """
          2013-05-18 * ""
            Assets:Investments:MSFT      10 MSFT {{2,000 USD}}
            Assets:Investments:Cash  -20000 USD

          2013-05-18 * ""
            Assets:Investments:MSFT      10 MSFT {{2000 USD / 2014-02-25}}
            Assets:Investments:Cash  -20000 USD
        """
        for entry in entries:
            posting = entry.postings[0]
            self.assertEqual(grammar.CompoundAmount(ZERO, D('2000'), 'USD'),
                             posting.position.lot.compound_cost)
            self.assertEqual(None, posting.price)


class TestMetaData(unittest.TestCase):

    @staticmethod
    def strip_meta(meta):
        """Removes the filename, lineno from the postings metadata."""
        copy = meta.copy()
        copy.pop('filename', None)
        copy.pop('lineno', None)
        return copy

    @parser.parse_doc()
    def test_metadata_transaction__begin(self, entries, errors, _):
        """
          2013-05-18 * ""
            test: "Something"
            Assets:Investments:MSFT      10 MSFT @@ 2000 USD
            Assets:Investments:Cash  -20000 USD
        """
        self.assertEqual(1, len(entries))
        self.assertEqual('Something', entries[0].meta['test'])

    @parser.parse_doc()
    def test_metadata_transaction__middle(self, entries, errors, _):
        """
          2013-05-18 * ""
            Assets:Investments:MSFT      10 MSFT @@ 2000 USD
            test: "Something"
            Assets:Investments:Cash  -20000 USD
        """
        self.assertEqual(1, len(entries))
        self.assertEqual({'test': 'Something'},
                         self.strip_meta(entries[0].postings[0].meta))

    @parser.parse_doc()
    def test_metadata_transaction__end(self, entries, errors, _):
        """
          2013-05-18 * ""
            Assets:Investments:MSFT      10 MSFT @@ 2000 USD
            Assets:Investments:Cash  -20000 USD
            test: "Something"
        """
        self.assertEqual(1, len(entries))
        self.assertEqual({'test': 'Something'},
                         self.strip_meta(entries[0].postings[1].meta))

    @parser.parse_doc()
    def test_metadata_transaction__many(self, entries, errors, _):
        """
          2013-05-18 * ""
            test1: "Something"
            Assets:Investments:MSFT      10 MSFT @@ 2000 USD
            test2: "has"
            test3: "to"
            Assets:Investments:Cash  -20000 USD
            test4: "come"
            test5: "from"
            test6: "this"
        """
        self.assertEqual(1, len(entries))
        self.assertEqual('Something', entries[0].meta['test1'])
        self.assertEqual({'test2': 'has', 'test3': 'to'},
                         self.strip_meta(entries[0].postings[0].meta))
        self.assertEqual({'test4': 'come', 'test5': 'from', 'test6': 'this'},
                         self.strip_meta(entries[0].postings[1].meta))

    @parser.parse_doc()
    def test_metadata_transaction__indented(self, entries, errors, _):
        """
          2013-05-18 * ""
              test1: "Something"
            Assets:Investments:MSFT      10 MSFT @@ 2000 USD
              test2: "has"
              test3: "to"
            Assets:Investments:Cash  -20000 USD
              test4: "come"
              test5: "from"
              test6: "this"
        """
        self.assertEqual(1, len(entries))
        self.assertEqual('Something', entries[0].meta['test1'])
        self.assertEqual({'test2': 'has', 'test3': 'to'},
                         self.strip_meta(entries[0].postings[0].meta))
        self.assertEqual({'test4': 'come', 'test5': 'from', 'test6': 'this'},
                         self.strip_meta(entries[0].postings[1].meta))

    @parser.parse_doc(expect_errors=True)
    def test_metadata_transaction__repeated(self, entries, errors, _):
        """
          2013-05-18 * ""
            test: "Bananas"
            test: "Apples"
            test: "Oranges"
            Assets:Investments   100 USD
              test: "Bananas"
              test: "Apples"
            Income:Investments  -100 USD
        """
        self.assertEqual(1, len(entries))
        self.assertEqual('Bananas', entries[0].meta['test'])
        self.assertEqual({'test': 'Bananas'},
                         self.strip_meta(entries[0].postings[0].meta))
        self.assertEqual(3, len(errors))
        self.assertTrue(all(re.search('Duplicate.*metadata field', error.message)
                            for error in errors))

    @parser.parse_doc()
    def test_metadata_empty(self, entries, errors, _):
        """
          2013-05-18 * "blabla"
            oranges:
            bananas:

          2013-05-19 open Assets:Something
            apples:
        """
        self.assertFalse(errors)
        self.assertEqual(2, len(entries))
        self.assertEqual({'oranges', 'bananas', 'filename', 'lineno'},
                         entries[0].meta.keys())
        self.assertEqual(None, entries[0].meta['oranges'])
        self.assertEqual(None, entries[0].meta['bananas'])
        self.assertEqual(entries[1].meta['apples'], None)

    @parser.parse_doc()
    def test_metadata_other(self, entries, errors, _):
        """
          2013-01-01 open Equity:Other

          2013-01-01 open Assets:Investments
            test1: "Something"
            test2: "Something"

          2014-01-01 close Assets:Investments
            test1: "Something"

          2013-01-10 note Assets:Investments "Bla"
            test1: "Something"

          2013-01-31 pad Assets:Investments Equity:Other
            test1: "Something"

          2013-02-01 balance Assets:Investments  111.00 USD
            test1: "Something"

          2013-03-01 event "location" "Nowhere"
            test1: "Something"

          2013-03-01 document Assets:Investments "/path/to/something.pdf"
            test1: "Something"

          2013-03-01 price  HOOL  500 USD
            test1: "Something"
        """
        self.assertEqual(9, len(entries))

    @parser.parse_doc()
    def test_metadata_data_types(self, entries, errors, _):
        """
          2013-05-18 * ""
            string: "Something"
            account: Assets:Investments:Cash
            date: 2012-01-01
            currency: HOOL
            tag: #trip-florida
            number: 345.67
            amount: 345.67 USD
            boolt: TRUE
            boolf: FALSE
        """
        self.assertEqual(1, len(entries))
        self.assertTrue('filename' in entries[0].meta)
        self.assertTrue('lineno' in entries[0].meta)
        del entries[0].meta['filename']
        del entries[0].meta['lineno']
        self.assertEqual({
            'string': 'Something',
            'account': 'Assets:Investments:Cash',
            'date': datetime.date(2012, 1, 1),
            'currency': 'HOOL',
            'tag': 'trip-florida',
            'number': D('345.67'),
            'amount': A('345.67 USD'),
            'boolt': True,
            'boolf': False,
            }, entries[0].meta)

    @parser.parse_doc()
    def test_metadata_key_syntax(self, entries, errors, _):
        """
          2013-05-18 * ""
            nameoncard: "Jim"
            nameOnCard: "Joe"
            name-on-card: "Bob"
            name_on_card: "John"
        """
        self.assertEqual(1, len(entries))
        self.assertLessEqual(set('nameoncard nameOnCard name-on-card name_on_card'.split()),
                             set(entries[0].meta.keys()))


class TestArithmetic(unittest.TestCase):

    maxDiff = None

    @parser.parse_doc()
    def test_number_expr__add(self, entries, errors, _):
        """
          2013-05-18 * "Test"
            Assets:Something    12 + 3 USD
            Assets:Something   7.5 + 3.1 USD
        """
        self.assertEqual(1, len(entries))
        postings = entries[0].postings
        self.assertEqual(D('15'), postings[0].position.number)
        self.assertEqual(D('10.6'), postings[1].position.number)

    @parser.parse_doc()
    def test_number_expr__subtract(self, entries, errors, _):
        """
          2013-05-18 * "Test"
            Assets:Something    12 - 3 USD
            Assets:Something   7.5 - 3.1 USD
        """
        self.assertEqual(1, len(entries))
        postings = entries[0].postings
        self.assertEqual(D('9'), postings[0].position.number)
        self.assertEqual(D('4.4'), postings[1].position.number)

    @parser.parse_doc()
    def test_number_expr__multiply(self, entries, errors, _):
        """
          2013-05-18 * "Test"
            Assets:Something    12 * 3 USD
            Assets:Something   7.5 * 3.1 USD
        """
        self.assertEqual(1, len(entries))
        postings = entries[0].postings
        self.assertEqual(D('36'), postings[0].position.number)
        self.assertEqual(D('23.25'), postings[1].position.number)

    @parser.parse_doc()
    def test_number_expr__divide(self, entries, errors, _):
        """
          2013-05-18 * "Test"
            Assets:Something    12 / 3 USD
            Assets:Something   7.5 / 3 USD
        """
        self.assertEqual(1, len(entries))
        postings = entries[0].postings
        self.assertEqual(D('4'), postings[0].position.number)
        self.assertEqual(D('2.5'), postings[1].position.number)

    @parser.parse_doc()
    def test_number_expr__negative(self, entries, errors, _):
        """
          2013-05-18 * "Test"
            Assets:Something    -12 USD
            Assets:Something   -7.5 USD
            Assets:Something   - 7.5 USD
        """
        self.assertEqual(1, len(entries))
        postings = entries[0].postings
        self.assertEqual(D('-12'), postings[0].position.number)
        self.assertEqual(D('-7.5'), postings[1].position.number)
        self.assertEqual(D('-7.5'), postings[2].position.number)

    @parser.parse_doc()
    def test_number_expr__positive(self, entries, errors, _):
        """
          2013-05-18 * "Test"
            Assets:Something    +12 USD
            Assets:Something   -7.5 USD
        """
        self.assertEqual(1, len(entries))
        postings = entries[0].postings
        self.assertEqual(D('12'), postings[0].position.number)

    @parser.parse_doc()
    def test_number_expr__precedence(self, entries, errors, _):
        """
          2013-05-18 * "Test"
            Assets:Something   2 * 3 + 4 USD
            Assets:Something   2 + 3 * 4 USD
            Assets:Something   2 + -3 * 4 USD
            Assets:Something   (2 + -3) * 4 USD
        """
        self.assertEqual(1, len(entries))
        self.assertListEqual(
            [D('10'), D('14'), D('-10'), D('-4')],
            [posting.position.number for posting in entries[0].postings])

    @parser.parse_doc()
    def test_number_expr__groups(self, entries, errors, _):
        """
          2013-05-18 * "Test"
            Assets:Something   (2 + -3) * 4 USD
            Assets:Something   2 * (2 + -3) USD
        """
        self.assertEqual(1, len(entries))
        self.assertListEqual(
            [D('-4'), D('-2')],
            [posting.position.number
             for posting in entries[0].postings])

    @parser.parse_doc()
    def test_number_expr__different_places(self, entries, errors, _):
        """
          2013-05-18 * "Test"
            Assets:Something   -(3 * 4) HOOL {120.01 * 2.1 USD} @ 134.02 * 2.1 USD
            Assets:Something   1000000 USD ;; No balance checks.
          2014-01-01 balance Assets:Something  3 * 4 * 120.01 * 2.1  USD
            number: -(5662.23 + 22.3)
        """
        self.assertFalse(errors)
        self.assertEqual(2, len(entries))
        self.assertEqual(D('-12'), entries[0].postings[0].position.number)
        self.assertEqual(D('252.021'),
                         entries[0].postings[0].position.lot.compound_cost.number_per)
        self.assertEqual(None,
                         entries[0].postings[0].position.lot.compound_cost.number_total)
        self.assertEqual(D('281.442'), entries[0].postings[0].price.number)
        self.assertEqual(D('3024.252'), entries[1].amount.number)
        self.assertEqual(D('-5684.53'), entries[1].meta['number'])


class TestLexerAndParserErrors(cmptest.TestCase):
    """There are a number of different paths where errors may occur. This test case
    intends to exercise them all. This docstring explains how it all works (it's
    a bit complicated).

    Expectations: The parser.parse_*() functions never raise exceptions, they
    always produce a list of error messages on the builder objects. This is by
    design: we have a single way to produce and report errors.

    The lexer may fail in two different ways:

    * Invalid Token: yylex() is invoked by the parser... the lexer rules are
      processed and all fail and the default rule of the lexer gets called at
      {bf253a29a820}. The lexer immediately switches to its INVALID subparser to
      chomp the rest of the invalid token's unrecognized characters until it
      hits some whitespace (see {bba169a1d35a}). A new LexerError is created and
      accumulated by calling the build_lexer_error() method on the builder
      object using this text (see {0e31aeca3363}). The lexer then returns a
      LEX_ERROR token to the parser, which fails as below.

    * Lexer Builder Exception: The lexer recognizes a valid token and invokes a
      callback on the builder using BUILD_LEX(). However, an exception is raised
      in that Python code ({3cfb2739349a}). The exception's error text is saved
      and this is used to build an error on the lexer builder at
      build_lexer_error().

    For both the errors above, when the parser receives the LEX_ERROR token, it
    is an unexpected token (because none of the rules handle it), so it calls
    yyerror() {ca6aab8b9748}. Because the lexer has already registered an error
    in the error list, in yyerror() we simply ignore it and do nothing (see
    {ca6aab8b9748}).

    Error recovery then proceeds by successive reductions of the "error" grammar
    rules which discards all tokens until a valid rule can be reduced again
    ({3d95e55b654e}). Note that Bison issues a single call to yyerror() and
    keeps reducing invalid "error" rules silently until another one succeeds. We
    ignore the directive and restart parsing from that point on. If the error
    occurred on a posting in progress of being parsed, because the "error" rule
    is not a valid posting of a transaction, that transaction will not be
    produced and thus is ignore, which is what we want.

    The parser may itself also encounter two similar types of errors:

    * Syntax Error: There is an error in the grammar of the input. yyparse() is
      called automatically by the generated code and we call
      build_grammar_error() to register the error. Error recovery proceeds
      similarly to what was described previously.

    * Grammar Builder Exception: A grammar rule is reduced succesfully, a
      builder method is invoked and raises a Python exception. A macro in the
      code that invokes this method is used to catch this error and calls
      build_grammar_error_from_exception() to register an error and makes the
      parser issue an error wth YYERROR (see {05bb0fb60e86}).

    We never call YYABORT anywhere so the yyparse() function should never return
    anything else than 0. If it does, we translate that into a Python
    RuntimeError exception, or a MemoryError exception (if yyparse() ran out of
    memory), see {459018e2905c}.
    """

    @parser.parse_doc(expect_errors=True)
    def test_lexer_invalid_token(self, entries, errors, _):
        """
          2000-01-01 open ) USD
        """
        self.assertEqual(0, len(entries))
        self.assertEqual(1, len(errors))
        self.assertRegexpMatches(errors[0].message, r"syntax error, unexpected RPAREN")

    @parser.parse_doc(expect_errors=True)
    def test_lexer_invalid_token__recovery(self, entries, errors, _):
        """
          2000-01-01 open ) USD
          2000-01-02 open Assets:Something
        """
        self.assertEqualEntries("""
          2000-01-02 open Assets:Something
        """, entries)
        self.assertEqual(1, len(errors))
        self.assertRegexpMatches(errors[0].message, r"syntax error, unexpected RPAREN")

    @parser.parse_doc(expect_errors=True)
    def test_lexer_exception(self, entries, errors, _):
        """
          2000-13-32 open Assets:Something
        """
        self.assertEqual(0, len(entries))
        self.assertEqual(1, len(errors))
        self.assertRegexpMatches(errors[0].message, 'month must be in 1..12')

    @parser.parse_doc(expect_errors=True)
    def test_lexer_exception__recovery(self, entries, errors, _):
        """
          2000-13-32 open Assets:Something
          2000-01-02 open Assets:Working
        """
        self.assertEqualEntries("""
          2000-01-02 open Assets:Working
        """, entries)
        self.assertEqual(1, len(entries))
        self.assertEqual(1, len(errors))
        self.assertRegexpMatches(errors[0].message, 'month must be in 1..12')

    def test_lexer_errors_in_postings(self):
        txn_strings = textwrap.dedent("""

          2000-01-02 *
            Assets:Working  `
            Assets:Working  11.11 USD
            Assets:Working  22.22 USD

          2000-01-02 *
            Assets:Working  11.11 USD
            Assets:Working  `
            Assets:Working  22.22 USD

          2000-01-02 *
            Assets:Working  11.11 USD
            Assets:Working  22.22 USD
            Assets:Working  `

          2000-01-02 *
            Assets:Working  )
            Assets:Working  11.11 USD
            Assets:Working  22.22 USD

          2000-01-02 *
            Assets:Working  11.11 USD
            Assets:Working  )
            Assets:Working  22.22 USD

          2000-01-02 *
            Assets:Working  11.11 USD
            Assets:Working  22.22 USD
            Assets:Working  )

        """).strip().split('\n\n')
        self.assertEqual(6, len(txn_strings))
        for txn_string in txn_strings:
            input_string = txn_string + textwrap.dedent("""
              2000-01-02 open Assets:Working
            """)
            entries, errors, _ = parser.parse_string(input_string)

            # Check that the transaction is not produced.
            self.assertEqualEntries("""
              2000-01-02 open Assets:Working
            """, entries)
            self.assertEqual(1, len(entries))
            self.assertEqual(1, len(errors))
            self.assertRegexpMatches(errors[0].message,
                                     '(Invalid token|unexpected RPAREN)')

    @parser.parse_doc(expect_errors=True)
    def test_grammar_syntax_error(self, entries, errors, _):
        """
          2000-01-01 open open
        """
        self.assertEqual(0, len(entries))
        self.assertEqual(1, len(errors))
        self.assertRegexpMatches(errors[0].message, r"syntax error")

    @parser.parse_doc(expect_errors=True)
    def test_grammar_syntax_error__recovery(self, entries, errors, _):
        """
          2000-01-01 open Assets:Before
          2000-01-02 open open
          2000-01-03 open Assets:After
        """
        self.assertEqual(1, len(errors))
        self.assertRegexpMatches(errors[0].message, r"syntax error")
        self.assertEqualEntries("""
          2000-01-01 open Assets:Before
          2000-01-03 open Assets:After
        """, entries)

    @parser.parse_doc(expect_errors=True)
    def test_grammar_syntax_error__recovery2(self, entries, errors, _):
        """
          2000-01-01 open open
          2000-01-02 open Assets:Something
        """
        self.assertEqual(1, len(errors))
        self.assertRegexpMatches(errors[0].message, r"syntax error")
        self.assertEqual(1, len(entries))
        self.assertEqualEntries("""
          2000-01-02 open Assets:Something
        """, entries)

    @parser.parse_doc(expect_errors=True)
    def test_grammar_syntax_error__multiple(self, entries, errors, _):
        """
          2000-01-01 open Assets:Before
          2000-01-02 open open
          2000-01-03 open Assets:After
          2000-01-04 close close
          2000-01-05 close Assets:After
        """
        self.assertEqual(2, len(errors))
        for error in errors:
            self.assertRegexpMatches(error.message, r"syntax error")
        self.assertEqual(3, len(entries))
        self.assertEqualEntries("""
          2000-01-01 open Assets:Before
          2000-01-03 open Assets:After
          2000-01-05 close Assets:After
        """, entries)

    def check_entries_errors(self, entries, errors):
        self.assertEqual(1, len(errors))
        self.assertRegexpMatches(errors[0].message, 'Patched exception')
        self.assertEqual(2, len(entries))

    @mock.patch('beancount.parser.grammar.Builder.pushtag', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__pushtag(self, entries, errors, _):
        """
          2000-01-01 open Assets:Before
          pushtag #sometag
          2010-01-01 close Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.poptag', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__poptag(self, entries, errors, _):
        """
          2000-01-01 open Assets:Before
          poptag #sometag
          2010-01-01 close Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.option', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__option(self, entries, errors, _):
        """
          2000-01-01 open Assets:Before
          option "operating_currency" "CAD"
          2010-01-01 close Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.include', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__include(self, entries, errors, _):
        """
          2000-01-01 open Assets:Before
          include "answer.beancount"
          2010-01-01 close Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.plugin', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__plugin(self, entries, errors, _):
        """
          2000-01-01 open Assets:Before
          plugin "answer.beancount"
          2010-01-01 close Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.amount', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__amount(self, entries, errors, _):
        """
          2000-01-01 open Assets:Before
          2001-02-02 balance Assets:Before    23.00 USD
          2010-01-01 close Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.compound_amount', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__compound_amount(self, entries, errors, _):
        """
          2000-01-01 open Assets:Before
          2001-02-02 *
            Assets:Before   10.00 HOOL {100.00 # 9.95 USD}
            Assets:After   -100.00 USD
          2010-01-01 close Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.lot_spec', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__lot_cost_date(self, entries, errors, _):
        """
          2000-01-01 open Assets:Before
          2001-02-02 *
            Assets:Before   10.00 HOOL {100.00 USD}
            Assets:After   -100.00 USD
          2010-01-01 close Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.position', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__position(self, entries, errors, _):
        """
          2000-01-01 open Assets:Before
          2001-02-02 *
            Assets:Before   100.00 USD
            Assets:After   -100.00 USD
          2010-01-01 close Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.open', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__open(self, entries, errors, _):
        """
          2010-01-01 balance Assets:Before  1 USD
          2000-01-01 open Assets:Before
          2010-01-01 close Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.close', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__close(self, entries, errors, _):
        """
          2010-01-01 balance Assets:Before  1 USD
          2010-01-01 close Assets:Before
          2000-01-01 open Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.commodity', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__commodity(self, entries, errors, _):
        """
          2010-01-01 close Assets:Before
          2010-01-01 commodity USD
          2000-01-01 open Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.pad', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__pad(self, entries, errors, _):
        """
          2010-01-01 close Assets:Before
          2010-01-01 pad Assets:Before Assets:After
          2000-01-01 open Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.balance', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__balance(self, entries, errors, _):
        """
          2010-01-01 close Assets:Before
          2010-01-01 balance Assets:Before 100 USD
          2000-01-01 open Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.event', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__event(self, entries, errors, _):
        """
          2010-01-01 close Assets:Before
          2010-01-01 event "location" "New York, NY"
          2000-01-01 open Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.price', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__price(self, entries, errors, _):
        """
          2010-01-01 close Assets:Before
          2010-01-01 price HOOL 20 USD
          2000-01-01 open Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.note', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__note(self, entries, errors, _):
        """
          2010-01-01 close Assets:Before
          2010-01-01 note Assets:Before "Something something"
          2000-01-01 open Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.document', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__document(self, entries, errors, _):
        """
          2010-01-01 close Assets:Before
          2010-01-01 document Assets:Before "/path/to/document.png"
          2000-01-01 open Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.key_value', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__key_value(self, entries, errors, _):
        """
          2010-01-01 close Assets:Before
          2010-01-01 commodity HOOL
            key: "Value"
          2000-01-01 open Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.posting', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__posting(self, entries, errors, _):
        """
          2010-01-01 close Assets:Before
          2010-01-01 *
            Assets:Before   100.00 USD
            Assets:After   -100.00 USD
          2000-01-01 open Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.txn_field_new', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__txn_field_new(self, entries, errors, _):
        """
          2010-01-01 close Assets:Before
          2010-01-01 * "Payee" "Narration"
            Assets:Before   100.00 USD
            Assets:After   -100.00 USD
          2000-01-01 open Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.txn_field_TAG', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__txn_field_TAG(self, entries, errors, _):
        """
          2010-01-01 close Assets:Before
          2010-01-01 * "Payee" "Narration" #sometag
            Assets:Before   100.00 USD
            Assets:After   -100.00 USD
          2000-01-01 open Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.txn_field_LINK', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__txn_field_LINK(self, entries, errors, _):
        """
          2010-01-01 close Assets:Before
          2010-01-01 * "Payee" "Narration" ^somelink
            Assets:Before   100.00 USD
            Assets:After   -100.00 USD
          2000-01-01 open Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.txn_field_STRING', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__txn_field_STRING(self, entries, errors, _):
        """
          2010-01-01 close Assets:Before
          2010-01-01 * "Payee" "Narration" ^somelink
            Assets:Before   100.00 USD
            Assets:After   -100.00 USD
          2000-01-01 open Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.txn_field_PIPE', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__txn_field_PIPE(self, entries, errors, _):
        """
          2010-01-01 close Assets:Before
          2010-01-01 * "Payee" | "Narration"
            Assets:Before   100.00 USD
            Assets:After   -100.00 USD
          2000-01-01 open Assets:Before
        """
        self.check_entries_errors(entries, errors)

    @mock.patch('beancount.parser.grammar.Builder.transaction', raise_exception)
    @parser.parse_doc(expect_errors=True)
    def test_grammar_exceptions__transaction(self, entries, errors, _):
        """
          2010-01-01 close Assets:Before
          2010-01-01 * "Payee" | "Narration"
            Assets:Before   100.00 USD
            Assets:After   -100.00 USD
          2000-01-01 open Assets:Before
        """
        self.check_entries_errors(entries, errors)


class TestIncompleteInputs(cmptest.TestCase):

    @parser.parse_doc(allow_incomplete=True)
    def test_missing_amount(self, entries, _, options_map):
        """
          2000-01-01 open Assets:Account1
          2000-01-01 open Assets:Account2
          2010-05-28 *
            Assets:Account1     100.00 USD
            Assets:Account2
        """
        self.assertEqual(None, entries[-1].postings[-1].position)

    @parser.parse_doc(allow_incomplete=True)
    def test_missing_number(self, entries, _, options_map):
        """
          2000-01-01 open Assets:Account1
          2000-01-01 open Assets:Account2
          2010-05-28 *
            Assets:Account1     100.00 USD
            Assets:Account2            CAD
        """
        pos = entries[-1].postings[-1].position
        self.assertFalse(pos is None)
        self.assertEqual(None, pos.number)
        self.assertEqual("CAD", pos.lot.currency)

    @parser.parse_doc(allow_incomplete=True)
    def test_missing_price_amount(self, entries, _, options_map):
        """
          2000-01-01 open Assets:Account1
          2000-01-01 open Assets:Account2
          2010-05-28 *
            Assets:Account1     100.00 USD @
            Assets:Account2     120.00 CAD
        """
        posting = entries[-1].postings[0]
        pos = posting.position
        self.assertEqual(D('100.00'), pos.number)
        self.assertEqual('USD', pos.lot.currency)
        self.assertIsInstance(posting.price, amount.Amount)
        self.assertEqual(amount.Amount(None, None), posting.price)

    @parser.parse_doc(allow_incomplete=True)
    def test_missing_price_number(self, entries, _, options_map):
        """
          2000-01-01 open Assets:Account1
          2000-01-01 open Assets:Account2
          2010-05-28 *
            Assets:Account1     100.00 USD @ CAD
            Assets:Account2     120.00 CAD
        """
        posting = entries[-1].postings[0]
        pos = posting.position
        self.assertEqual(D('100.00'), pos.number)
        self.assertEqual('USD', pos.lot.currency)
        self.assertEqual(None, pos.lot.compound_cost)
        self.assertIsInstance(posting.price, amount.Amount)
        self.assertEqual(amount.Amount(None, 'CAD'), posting.price)

    @parser.parse_doc(allow_incomplete=True)
    def test_missing_cost_amount(self, entries, _, options_map):
        """
          2000-01-01 open Assets:Account1
          2000-01-01 open Assets:Account2
          2010-05-28 *
            Assets:Account1     2 HOOL {}
            Assets:Account2     120.00 CAD
        """
        posting = entries[-1].postings[0]
        pos = posting.position
        self.assertEqual(D('2'), pos.number)
        self.assertIsInstance(pos.lot, position.LotSpec)
        self.assertEqual(position.LotSpec('HOOL', None, None, None, None), pos.lot)

    @parser.parse_doc(allow_incomplete=True)
    def test_missing_cost_number(self, entries, _, options_map):
        """
          2000-01-01 open Assets:Account1
          2000-01-01 open Assets:Account2
          2010-05-28 *
            Assets:Account1     2 HOOL {USD}
            Assets:Account2     120.00 USD
        """
        posting = entries[-1].postings[0]
        pos = posting.position
        self.assertEqual(D('2'), pos.number)
        self.assertIsInstance(pos.lot, position.LotSpec)
        self.assertEqual(
            position.LotSpec('HOOL',
                             grammar.CompoundAmount(None, None, 'USD'), None, None, None),
            pos.lot)
