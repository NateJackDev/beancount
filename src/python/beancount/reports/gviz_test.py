__author__ = "Martin Blais <blais@furius.ca>"

import unittest
import datetime
import random
import re

from beancount.reports import gviz


class TestGviz(unittest.TestCase):

    def test_gviz_timeline(self):
        times = [datetime.datetime(2010, 3, 3),
                 datetime.datetime(2010, 3, 17),
                 datetime.datetime(2010, 3, 19),
                 datetime.datetime(2010, 4, 7),
                 datetime.datetime(2010, 4, 8),
                 datetime.datetime(2010, 4, 8),
                 datetime.datetime(2010, 4, 10),
                 datetime.datetime(2010, 7, 1),
                 datetime.datetime(2010, 8, 22)]
        data = {
            'x': [random.random() * 20 for _ in range(len(times))],
            'y': [random.random() * 15 for _ in range(len(times))],
            'z': [random.random() * 15 for _ in range(len(times) + 2)],
        }
        html = gviz.gviz_timeline(times, data)
        self.assertTrue(isinstance(html, str))

        self.assertTrue(re.search(r'\bx\b', html))
        self.assertTrue(re.search(r'\by\b', html))
        self.assertTrue(re.search(r'\bz\b', html))
        self.assertTrue(re.search(r'\.visualization\.AnnotatedTimeLine', html))
        self.assertTrue(re.search(r'\.setOnLoadCallback', html))
