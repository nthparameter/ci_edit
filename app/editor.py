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
"""Interactive UIs for the ciEditor."""

try:
    unicode
except NameError:
    unicode = str
    unichr = chr

import os
import re

import app.config
import app.controller
import app.text_buffer

def parse_int(in_str):
    if app.config.strict_debug:
        assert isinstance(in_str, unicode), type(in_str)
    i = 0
    k = 0
    if len(in_str) > i and in_str[i] in ("+", "-"):
        i += 1
    k = i
    while len(in_str) > k and in_str[k].isdigit():
        k += 1
    if k > i:
        return int(in_str[:k])
    return 0

def test_parse_int():
    assert parse_int("0") == 0
    assert parse_int("0e") == 0
    assert parse_int("text") == 0
    assert parse_int("10") == 10
    assert parse_int("+10") == 10
    assert parse_int("-10") == -10
    assert parse_int("--10") == 0
    assert parse_int("--10") == 0

class InteractivePrediction(app.controller.Controller):
    """Make a guess about what the user desires."""

    def __init__(self, view):
        if app.config.strict_debug:
            assert issubclass(self.__class__, InteractivePrediction), self
            assert issubclass(view.__class__, app.window.ViewWindow), view
        app.controller.Controller.__init__(self, view, "prediction")

    def cancel(self):
        self.items = [(self.prior_text_buffer, self.prior_text_buffer.full_path, "")]
        self.index = 0
        self.change_to_host_window()

    def cursor_move_to(self, row, col):
        if app.config.strict_debug:
            assert isinstance(row, int)
            assert isinstance(col, int)
        text_buffer = self.view.host.text_buffer
        text_buffer.cursor_move_to(row, col)
        text_buffer.cursor_scroll_to_middle()
        text_buffer.redo()

    def focus(self):
        app.log.info("InteractivePrediction.focus")
        app.controller.Controller.focus(self)
        self.prior_text_buffer = self.view.host.text_buffer
        self.index = self.build_file_list(self.view.host.text_buffer.full_path)
        self.view.host.set_text_buffer(text_buffer.TextBuffer())
        self.command_default = self.view.text_buffer.insert_printable
        self.view.host.text_buffer.line_limit_indicator = 0
        self.view.host.text_buffer.root_grammar = self.view.program.prefs.get_grammar(
            "_pre"
        )

    def info(self):
        app.log.info("InteractivePrediction command set")

    def build_file_list(self, current_file):
        if app.config.strict_debug:
            assert isinstance(current_file, str)
        self.items = []
        buffer_manager = self.view.program.buffer_manager
        for i in buffer_manager.buffers:
            dirty = "*" if i.is_dirty() else "."
            if i.full_path:
                self.items.append((i, i.full_path, dirty))
            else:
                self.items.append(
                    (i, f"<new file> {i.parser.row_text(0)[:20]}", dirty)
                )
        dir_path, file_name = os.path.split(current_file)
        file_name, ext = os.path.splitext(file_name)
        # TODO(dschuyler): rework this ignore list.
        ignoreExt = set(
            (
                ".pyc",
                ".pyo",
                ".o",
                ".obj",
                ".tgz",
                ".zip",
                ".tar",
            )
        )
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
                self.items.append((None, os.path.join(dir_path, i), "="))
        if 1:
            app.log.info()
            # Chromium specific hack.
            if current_file.endswith("-extracted.js"):
                chromium_path = current_file[: -len("-extracted.js")] + ".html"
                app.log.info(chromium_path)
                if os.path.isfile(chromium_path):
                    app.log.info()
                    self.items.append((None, chromium_path, "="))
            elif current_file.endswith(".html"):
                app.log.info()
                chromium_path = current_file[: -len(".html")] + "-extracted.js"
                if os.path.isfile(chromium_path):
                    app.log.info()
                    self.items.append((None, chromium_path, "="))
        # Suggest item.
        return (len(buffer_manager.buffers) - 2) % len(self.items)

    def on_change(self):
        assert False
        clip = []
        limit = max(5, self.view.host.cols - 10)
        for i, item in enumerate(self.items):
            prefix = "-->" if i == self.index else "   "
            suffix = " <--" if i == self.index else ""
            clip.append(f"{prefix} {item[1][-limit:]} {item[2]}{suffix}")
        self.view.host.text_buffer.selection_all()
        self.view.host.text_buffer.edit_paste_lines(tuple(clip))
        self.cursor_move_to(self.index, 0)

    def next_item(self):
        self.index = (self.index + 1) % len(self.items)

    def prior_item(self):
        self.index = (self.index - 1) % len(self.items)

    def select_item(self):
        self.change_to_host_window()

    def unfocus(self):
        app.controller.Controller.unfocus(self)
        if self.items is None:
            return
        buffer_manager = self.view.program.buffer_manager
        text_buffer, full_path = self.items[self.index][:2]
        if text_buffer is not None:
            self.view.host.set_text_buffer(
                buffer_manager.get_valid_text_buffer(text_buffer)
            )
        else:
            expanded_path = os.path.abspath(os.path.expanduser(full_path))
            text_buffer = buffer_manager.load_text_buffer(expanded_path)
            self.view.host.set_text_buffer(text_buffer)
        self.items = None

class InteractiveFind(app.controller.Controller):
    """Find text within the current document."""

    def __init__(self, view):
        if app.config.strict_debug:
            assert issubclass(self.__class__, InteractiveFind), self
            assert issubclass(view.__class__, app.window.ViewWindow), view
        app.controller.Controller.__init__(self, view, "find")

    def find_next(self):
        self.find_cmd = self.view.host.text_buffer.find_next

    def find_prior(self):
        self.find_cmd = self.view.host.text_buffer.find_prior

    def focus(self):
        self.find_cmd = self.view.host.text_buffer.find
        selection = self.view.host.text_buffer.get_selected_text()
        if selection:
            self.view.find_line.text_buffer.selection_all()
            # Make a single regex line.
            selection = "\\n".join(selection)
            app.log.info(selection)
            self.view.find_line.text_buffer.insert(re.escape(selection))
        self.view.find_line.text_buffer.selection_all()

    def on_change(self):
        self.view.find_line.text_buffer.parse_screen_maybe()
        search_for = self.view.find_line.text_buffer.parser.row_text(0)
        try:
            self.find_cmd(search_for)
        except re.error as e:
            if hasattr(e, "msg"):
                self.error = e.msg
            elif hasattr(e, "message"):
                self.error = e.message
            else:
                self.error = "invalid regex"
        self.find_cmd = self.view.host.text_buffer.find

    def replace_and_next(self):
        replace_with = self.view.replace_line.text_buffer.parser.row_text(0)
        self.view.host.text_buffer.replace_found(replace_with)
        self.find_cmd = self.view.host.text_buffer.find_next

    def replace_and_prior(self):
        replace_with = self.view.replace_line.text_buffer.parser.row_text(0)
        self.view.host.text_buffer.replace_found(replace_with)
        self.find_cmd = self.view.host.text_buffer.find_prior

class InteractiveFindInput(app.controller.Controller):
    """Find text within the current document."""

    def __init__(self, view):
        if app.config.strict_debug:
            assert issubclass(self.__class__, InteractiveFindInput), self
            assert issubclass(view.__class__, app.window.ViewWindow), view
        app.controller.Controller.__init__(self, view, "find")

    def next_focusable_window(self):
        self.view.parent.expand_find_window(True)
        app.controller.Controller.next_focusable_window(self)

    # def prior_focusable_window(self):
    #  if not app.controller.Controller.prior_focusable_window(self):
    #    self.view.host.expand_find_window(False)

    def find_next(self):
        self.parent_controller().find_next()

    def find_prior(self):
        self.parent_controller().find_prior()

    def info(self):
        app.log.info("InteractiveFind command set")

    def on_change(self):
        self.parent_controller().on_change()

    def replace_and_next(self):
        self.parent_controller().replace_and_next()

    def replace_and_prior(self):
        self.parent_controller().replace_and_prior()

class InteractiveGoto(app.controller.Controller):
    """Jump to a particular line number."""

    def __init__(self, view):
        if app.config.strict_debug:
            assert issubclass(self.__class__, InteractiveGoto), self
            assert issubclass(view.__class__, app.window.ViewWindow), view
        app.controller.Controller.__init__(self, view, "goto")

    def focus(self):
        app.log.info("InteractiveGoto.focus")
        self.text_buffer.selection_all()
        self.text_buffer.insert(unicode(self.view.host.text_buffer.pen_row + 1))
        self.text_buffer.selection_all()

    def info(self):
        app.log.info("InteractiveGoto command set")

    def goto_bottom(self):
        app.log.info()
        self.text_buffer.selection_all()
        self.text_buffer.insert(unicode(self.view.host.text_buffer.parser.row_count()))
        self.change_to_host_window()

    def goto_halfway(self):
        self.text_buffer.selection_all()
        self.text_buffer.insert(
            unicode(self.view.host.text_buffer.parser.row_count() // 2 + 1)
        )
        self.change_to_host_window()

    def goto_top(self):
        self.text_buffer.selection_all()
        self.text_buffer.insert("0")
        self.change_to_host_window()

    def cursor_move_to(self, row, col):
        if app.config.strict_debug:
            assert isinstance(row, int)
            assert isinstance(col, int)
        text_buffer = self.view.host.text_buffer
        text_buffer.cursor_move_to(row, col)
        text_buffer.cursor_scroll_to_middle()
        text_buffer.redo()

    def on_change(self):
        app.log.info()
        self.text_buffer.parse_document()
        line = self.text_buffer.parser.row_text(0)
        goto_line, goto_col = (line.split(",") + ["0", "0"])[:2]
        self.cursor_move_to(parse_int(goto_line) - 1, parse_int(goto_col))

class ToggleController(app.controller.Controller):
    def __init__(self, view):
        if app.config.strict_debug:
            assert issubclass(self.__class__, ToggleController), self
            assert issubclass(view.__class__, app.window.ViewWindow), view
        app.controller.Controller.__init__(self, view, "toggle")

    def clear_value(self):
        category = self.view.pref_category
        name = self.view.pref_name
        prefs = self.view.program.prefs
        prefs.save(category, name, None)
        self.view.on_pref_changed(category, name)

    def toggle_value(self):
        category = self.view.pref_category
        name = self.view.pref_name
        prefs = self.view.program.prefs
        prefs.save(category, name, not prefs.category(category)[name])
        self.view.on_pref_changed(category, name)
