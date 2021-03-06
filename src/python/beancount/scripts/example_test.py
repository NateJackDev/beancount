__author__ = "Martin Blais <blais@furius.ca>"

from beancount.utils import test_utils
from beancount.scripts import example
from beancount.ops import validation
from beancount import loader


class TestScriptExample(test_utils.TestCase):

    def test_generate(self):
        # Basic test that calls out the generator.
        with test_utils.capture() as stdout:
            result = test_utils.run_with_args(example.main, [])
        self.assertEqual(0, result, str(result))
        file_contents = stdout.getvalue()
        self.assertTrue(file_contents)

        loaded_entries, errors, _ = loader.load_string(
            file_contents,
            extra_validations=validation.HARDCORE_VALIDATIONS)
        self.assertFalse(errors)
