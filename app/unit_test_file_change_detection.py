# Copyright 2024 Google Inc.
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

import os
import tempfile
import time
import unittest

import app.ci_program
import app.log
import app.text_buffer


class FileChangeDetectionTestCases(unittest.TestCase):
    def setUp(self):
        app.log.should_write_print_log = False
        self.prg = app.ci_program.CiProgram()
        self.text_buffer = app.text_buffer.TextBuffer(self.prg)

    def test_no_file_stat_returns_false(self):
        """has_file_changed returns False when file_stat is None."""
        self.assertIsNone(self.text_buffer.file_stat)
        self.assertFalse(self.text_buffer.has_file_changed())

    def test_no_full_path_returns_false(self):
        """has_file_changed returns False when full_path is empty."""
        self.text_buffer.full_path = ""
        self.assertFalse(self.text_buffer.has_file_changed())

    def test_unchanged_file_returns_false(self):
        """has_file_changed returns False when file has not been modified."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         delete=False) as f:
            f.write("hello world\n")
            path = f.name
        try:
            self.text_buffer.full_path = path
            self.text_buffer.file_stat = os.stat(path)
            self.assertFalse(self.text_buffer.has_file_changed())
        finally:
            os.unlink(path)

    def test_modified_file_returns_true(self):
        """has_file_changed returns True when file content changes."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         delete=False) as f:
            f.write("hello world\n")
            path = f.name
        try:
            self.text_buffer.full_path = path
            self.text_buffer.file_stat = os.stat(path)
            # Ensure mtime changes (some filesystems have 1s granularity).
            time.sleep(0.05)
            with open(path, "w") as f:
                f.write("changed content\n")
            self.assertTrue(self.text_buffer.has_file_changed())
        finally:
            os.unlink(path)

    def test_deleted_file_returns_false(self):
        """has_file_changed returns False when file is deleted (OSError)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         delete=False) as f:
            f.write("hello world\n")
            path = f.name
        self.text_buffer.full_path = path
        self.text_buffer.file_stat = os.stat(path)
        os.unlink(path)
        self.assertFalse(self.text_buffer.has_file_changed())

    def test_replaced_file_detected_by_inode(self):
        """has_file_changed detects save-by-rename via st_ino change."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         delete=False, dir="/tmp") as f:
            f.write("original\n")
            path = f.name
        try:
            self.text_buffer.full_path = path
            self.text_buffer.file_stat = os.stat(path)
            # Simulate save-by-rename: write to temp, rename over original.
            tmp_path = path + ".tmp"
            with open(tmp_path, "w") as f:
                f.write("original\n")  # Same content, but different inode.
            os.rename(tmp_path, path)
            self.assertTrue(self.text_buffer.has_file_changed())
        finally:
            if os.path.exists(path):
                os.unlink(path)
