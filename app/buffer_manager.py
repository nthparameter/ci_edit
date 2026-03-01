# Copyright 2016 Google Inc.
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

# For Python 2to3 support.

try:
    unicode
except NameError:
    unicode = str  # redefined-builtin
    unichr = chr

import os
import sys

import app.buffer_file
import app.config
import app.log
import app.history
import app.text_buffer

class BufferManager:
    """Manage a set of text buffers. Some text buffers may be hidden."""

    def __init__(self, program, prefs):
        if app.config.strict_debug:
            assert issubclass(self.__class__, BufferManager), self
        self.program = program
        self.prefs = prefs
        # Using a dictionary lookup for buffers accelerates finding buffers by
        # key (the file path), but that's not the common use. Maintaining an
        # ordered list turns out to be more valuable.
        self.buffers = []

    def close_text_buffer(self, text_buffer):
        """Warning this will throw away the buffer. Please be sure the user is
        ok with this before calling."""
        if app.config.strict_debug:
            assert issubclass(self.__class__, BufferManager), self
            assert issubclass(text_buffer.__class__, app.text_buffer.TextBuffer)
        self.untrack_buffer_(text_buffer)

    def get_unsaved_buffer(self):
        for file_buffer in self.buffers:
            if file_buffer.is_dirty():
                return file_buffer
        return None

    def new_text_buffer(self):
        text_buffer = app.text_buffer.TextBuffer(self.program)
        self.buffers.append(text_buffer)
        app.log.info(text_buffer)
        self.debug_log()
        return text_buffer

    def next_buffer(self):
        app.log.info()
        self.debug_log()
        if len(self.buffers):
            return self.buffers[0]
        return None

    def top_buffer(self):
        app.log.info()
        self.debug_log()
        if len(self.buffers):
            return self.buffers[-1]
        return None

    def get_valid_text_buffer(self, text_buffer):
        """If |text_buffer| is a managed buffer return it, otherwise create a new
        buffer. Primarily used to determine if a held reference to a text_buffer
        is still valid."""
        if text_buffer in self.buffers:
            del self.buffers[self.buffers.index(text_buffer)]
            self.buffers.append(text_buffer)
            return text_buffer
        text_buffer = app.text_buffer.TextBuffer(self.program)
        self.buffers.append(text_buffer)
        return text_buffer

    def load_text_buffer(self, rel_path):
        if app.config.strict_debug:
            assert issubclass(self.__class__, BufferManager), self
            assert isinstance(rel_path, unicode), type(rel_path)
        full_path = app.buffer_file.expand_full_path(rel_path)
        app.log.info(full_path)
        text_buffer = None
        for i, tb in enumerate(self.buffers):
            if tb.full_path == full_path:
                text_buffer = tb
                del self.buffers[i]
                self.buffers.append(tb)
                break
        app.log.info("Searched for text_buffer", repr(text_buffer))
        if not text_buffer:
            if os.path.isdir(full_path):
                app.log.info("Tried to open directory as a file", full_path)
                return
            if not os.path.isfile(full_path):
                app.log.info("creating a new file at\n ", full_path)
            text_buffer = app.text_buffer.TextBuffer(self.program)
            text_buffer.set_file_path(full_path)
            text_buffer.file_load()
            self.buffers.append(text_buffer)
        if 0:
            self.debug_log()
        return text_buffer

    def debug_log(self):
        buffer_list = ""
        for i in self.buffers:
            buffer_list += "\n  " + repr(i.full_path)
            buffer_list += "\n    " + repr(i)
            buffer_list += "\n    dirty: " + str(i.is_dirty())
        app.log.info("BufferManager" + buffer_list)

    def read_stdin(self):
        app.log.info("reading from stdin")
        # Create a new input stream for the file data.
        # Fd is short for file descriptor. os.dup and os.dup2 will duplicate
        # file descriptors.
        stdin_fd = sys.stdin.fileno()
        new_fd = os.dup(stdin_fd)
        new_stdin = open("/dev/tty")
        os.dup2(new_stdin.fileno(), stdin_fd)
        # Create a text buffer to read from alternate stream.
        text_buffer = self.new_text_buffer()
        try:
            with open(new_fd, "r") as fileInput:
                text_buffer.file_filter(fileInput.read())
        except Exception as e:
            app.log.exception(e)
        app.log.info("finished reading from stdin")
        return text_buffer

    def untrack_buffer_(self, file_buffer):
        app.log.debug(file_buffer.full_path)
        self.buffers.remove(file_buffer)

    def file_close(self, path):
        pass
