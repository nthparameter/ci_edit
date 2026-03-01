# Copyright 2018 Google Inc.
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

try:
    unicode
except NameError:
    unicode = str
    unichr = chr

import os
import re
import time
import warnings

import app.buffer_file
import app.controller
import app.string

class PredictionListController(app.controller.Controller):
    """Gather and prepare file directory information."""

    def __init__(self, view):
        assert self is not view
        app.controller.Controller.__init__(self, view, "PredictionListController")
        self.filter = None
        # |items| is a tuple of: buffer, path, flags, type.
        self.items = None
        self.shown_list = None

    def _build_file_list(self, current_file):
        if app.config.strict_debug:
            assert isinstance(current_file, unicode), repr(current_file)

        added = set()
        items = self.items = []
        if 1:
            # Add open buffers.
            def add_buffer(items, buffer, prediction):
                dirty = "*" if buffer.is_dirty() else "."
                if buffer.full_path:
                    items.append((buffer, buffer.full_path, dirty, "open", prediction))
                    added.add(buffer.full_path)
                else:
                    items.append(
                        (
                            buffer,
                            f"<new file> {buffer.parser.row_text(0)[:20]}",
                            dirty,
                            "open",
                            prediction,
                        )
                    )

            buffer_manager = self.view.program.buffer_manager
            # Add the most resent buffer to allow flipping back and forth
            # between two files.
            if len(buffer_manager.buffers) >= 2:
                add_buffer(items, buffer_manager.buffers[-2], 30000)
            order = 39999
            for i in buffer_manager.buffers[:-2]:
                add_buffer(items, i, order)
                order -= 1
            # This is the current buffer. It's unlikely to be the goal.
            if len(buffer_manager.buffers) >= 1:
                add_buffer(items, buffer_manager.buffers[-1], 90000)
        if 1:
            # Add recent files.
            for recent_file in self.view.program.history.get_recent_files():
                if recent_file not in added:
                    items.append((None, recent_file, "=", "recent", 50000))
                    added.add(recent_file)
        if 1:
            # Add alternate files.
            dir_path, file_name = os.path.split(current_file)
            file_name, ext = os.path.splitext(file_name)
            # TODO(dschuyler): rework this ignore list.
            ignoreExt = set((".pyc", ".pyo", ".o", ".obj", ".tgz", ".zip", ".tar"))
            try:
                contents = os.listdir(
                    os.path.expandvars(os.path.expanduser(dir_path)) or "."
                )
            except OSError:
                contents = []
            contents.sort()
            for i in contents:
                f, e = os.path.splitext(i)
                if file_name == f and ext != e and e not in ignoreExt:
                    full_path = os.path.join(dir_path, i)
                    if full_path not in added:
                        items.append((None, full_path, "=", "alt", 20000))
                        added.add(full_path)
            if 1:
                # Chromium specific hack.
                if current_file.endswith("-extracted.js"):
                    chromium_path = current_file[: -len("-extracted.js")] + ".html"
                    if os.path.isfile(chromium_path) and chromium_path not in added:
                        items.append((None, chromium_path, "=", "alt", 20000))
                        added.add(chromium_path)
                elif current_file.endswith(".html"):
                    chromium_path = current_file[: -len(".html")] + "-extracted.js"
                    if os.path.isfile(chromium_path) and chromium_path not in added:
                        items.append((None, chromium_path, "=", "alt", 20000))
                        added.add(chromium_path)
        if self.filter is not None:
            try:
                with warnings.catch_warnings():
                    # Ignore future warning with '[[' regex.
                    warnings.simplefilter("ignore")
                    regex = re.compile(self.filter)
                i = 0
                while i < len(items):
                    if not regex.search(items[i][1]):
                        # Filter the list in-place.
                        items.pop(i)
                    else:
                        i += 1
            except re.error:
                self.view.text_buffer.set_message("invalid regex")

    def focus(self):
        # app.log.info('PredictionListController')
        self.on_change()
        app.controller.Controller.focus(self)

    def info(self):
        app.log.info("PredictionListController command set")

    def on_change(self):
        controller = self.view.parent.prediction_input_window.controller
        self.filter = controller.decoded_path()
        if self.shown_list == self.filter:
            return
        self.shown_list = self.filter

        input_window = self.current_input_window()
        self._build_file_list(input_window.text_buffer.full_path)
        if self.items is not None:
            self.view.update(self.items)
        self.filter = None

    def open_alt_file(self):
        for row, item in enumerate(self.items):
            if item[3] == "alt":
                self.open_file_or_dir(row)

    def open_file_or_dir(self, row):
        if app.config.strict_debug:
            assert isinstance(row, int)
        if self.items is None or len(self.items) == 0:
            return
        buffer_manager = self.view.program.buffer_manager
        text_buffer, full_path = self.items[row][:2]
        self.items = None
        self.shown_list = None
        if text_buffer is not None:
            text_buffer = buffer_manager.get_valid_text_buffer(text_buffer)
        else:
            expanded_path = os.path.abspath(os.path.expanduser(full_path))
            text_buffer = buffer_manager.load_text_buffer(expanded_path)
        input_window = self.current_input_window()
        input_window.set_text_buffer(text_buffer)
        self.change_to(input_window)

    def option_changed(self, name, value):
        if app.config.strict_debug:
            assert isinstance(name, unicode)
            assert isinstance(value, unicode)
        self.shown_list = None
        self.on_change()

    def set_filter(self, list_filter):
        if app.config.strict_debug:
            assert isinstance(list_filter, unicode)
        self.filter = list_filter
        self.shown_list = None  # Cause a refresh.

    def unfocus(self):
        self.items = None
        self.shown_list = None

class PredictionController(app.controller.Controller):
    """Create or open files."""

    def __init__(self, view):
        app.controller.Controller.__init__(self, view, "PredictionController")

    def perform_primary_action(self):
        self.view.path_window.controller.perform_primary_action()

    def info(self):
        app.log.info("PredictionController command set")

    def on_change(self):
        # app.log.info('PredictionController')
        self.view.prediction_list.controller.on_change()
        app.controller.Controller.on_change(self)

    def option_changed(self, name, value):
        self.view.prediction_list.controller.shown_list = None

    def pass_event_to_prediction_list(self):
        self.view.prediction_list.controller.do_command(self.saved_ch, None)

class PredictionInputController(app.controller.Controller):
    """Manipulate query string."""

    def __init__(self, view):
        app.controller.Controller.__init__(self, view, "PredictionInputController")

    def decoded_path(self):
        if app.config.strict_debug:
            assert self.view.text_buffer is self.text_buffer
        return app.string.path_decode(self.text_buffer.parser.row_text(0))

    def set_encoded_path(self, path):
        if app.config.strict_debug:
            assert isinstance(path, unicode)
            assert self.view.text_buffer is self.text_buffer
        return self.text_buffer.replace_lines((app.string.path_encode(path),))

    def focus(self):
        # app.log.info('PredictionInputController')
        self.set_encoded_path("")
        # self.get_named_window('prediction_list').controller.set_filter("py")
        self.get_named_window("prediction_list").focus()
        app.controller.Controller.focus(self)

    def info(self):
        app.log.info("PredictionInputController command set")

    def on_change(self):
        # app.log.info('PredictionInputController', self.view.parent.get_path())
        self.get_named_window("prediction_list").controller.on_change()
        app.controller.Controller.on_change(self)

    def option_changed(self, name, value):
        if app.config.strict_debug:
            assert isinstance(name, unicode)
            assert isinstance(value, unicode)
        self.get_named_window("prediction_list").controller.shown_list = None

    def pass_event_to_prediction_list(self):
        self.get_named_window("prediction_list").controller.do_command(
            self.saved_ch, None
        )

    def open_alternate_file(self):
        app.log.info("PredictionInputController")
        prediction_list = self.get_named_window("prediction_list")
        prediction_list.controller.open_alt_file()

    def perform_primary_action(self):
        app.log.info("PredictionInputController")
        prediction_list = self.get_named_window("prediction_list")
        row = prediction_list.text_buffer.pen_row
        prediction_list.controller.open_file_or_dir(row)

    def prediction_list_next(self):
        prediction_list = self.get_named_window("prediction_list")
        if (
            prediction_list.text_buffer.pen_row
            == prediction_list.text_buffer.parser.row_count() - 1
        ):
            prediction_list.text_buffer.cursor_move_to(0, 0)
        else:
            prediction_list.text_buffer.cursor_down()

    def prediction_list_prior(self):
        prediction_list = self.get_named_window("prediction_list")
        if prediction_list.text_buffer.pen_row == 0:
            prediction_list.text_buffer.cursor_move_to(
                prediction_list.text_buffer.parser.row_count(), 0
            )
        else:
            prediction_list.text_buffer.cursor_up()

    def unfocus(self):
        self.get_named_window("prediction_list").unfocus()
        app.controller.Controller.unfocus(self)
