# Copyright 2019 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import curses
import unittest

import app.string

class StringTestCases(unittest.TestCase):
    def test_path_encode(self):
        tests = [
            ("abcd", "abcd"),
            ("\rabcd", "\\rabcd"),
            ("ab\rcd", "ab\\rcd"),
            ("abcd\r", "abcd\\r"),
            ("\aab\tcd\r", "\\aab\\tcd\\r"),
            ("abcd\\", "abcd\\\\"),
            ("\\", "\\\\"),
        ]
        for test in tests:
            self.assertEqual(app.string.path_encode(test[0]), test[1])
            self.assertEqual(app.string.path_decode(test[1]), test[0])
