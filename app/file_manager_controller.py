# Copyright 2017 Google Inc.
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

import app.buffer_file
import app.config
import app.controller
import app.string

class DirectoryListController(app.controller.Controller):
    """Gather and prepare file directory information."""

    def __init__(self, view):
        if app.config.strict_debug:
            assert self is not view
        app.controller.Controller.__init__(self, view, "DirectoryListController")
        self.filter = None
        self.shown_directory = None

    def focus(self):
        self.on_change()
        app.controller.Controller.focus(self)

    def info(self):
        app.log.info("DirectoryListController command set")

    def on_change(self):
        path_input = self.view.parent.path_window.controller.decoded_path()
        if self.shown_directory == path_input:
            return
        self.shown_directory = path_input
        app_prefs = self.view.program.prefs
        full_path, open_to_row, open_to_column = app.buffer_file.path_row_column(
            path_input, app_prefs.editor["base_dir_env"]
        )
        full_path = app.buffer_file.expand_full_path(full_path)
        dir_path = full_path
        file_name = ""
        if len(path_input) > 0 and path_input[-1] != os.sep:
            dir_path, file_name = os.path.split(full_path)
            self.view.text_buffer.find_re = re.compile("()^" + re.escape(file_name))
        else:
            self.view.text_buffer.find_re = None
        dir_path = dir_path or "."
        if os.path.isdir(dir_path):
            show_dot_files = app_prefs.editor["files_show_dot_files"]
            show_sizes = app_prefs.editor["files_show_sizes"]
            show_modified = app_prefs.editor["files_show_modified_dates"]

            sort_by_name = app_prefs.editor["files_sort_ascending_by_name"]
            sort_by_size = app_prefs.editor["files_sort_ascending_by_size"]
            sort_by_modified_date = app_prefs.editor["files_sort_ascending_by_modified_date"]

            lines = []
            try:
                file_lines = []
                dir_contents = os.listdir(dir_path)
                for dir_item in dir_contents:
                    if not show_dot_files and dir_item[0] == ".":
                        continue
                    if self.filter is not None and not dir_item.startswith(self.filter):
                        continue
                    full_path = os.path.join(dir_path, dir_item)
                    if os.path.isdir(full_path):
                        dir_item += os.path.sep
                    i_size = None
                    i_modified = 0
                    if show_sizes and os.path.isfile(full_path):
                        i_size = os.path.getsize(full_path)
                    if show_modified:
                        i_modified = os.path.getmtime(full_path)
                    # Handle \r and similar characters in file paths.
                    encoded_path = app.string.path_encode(dir_item)
                    file_lines.append([encoded_path, i_size, i_modified, dir_item])
                if sort_by_size is not None:
                    # Sort by size.
                    file_lines.sort(
                        reverse=not sort_by_size,
                        key=lambda x: x[1] if x[1] is not None else -1,
                    )
                elif sort_by_modified_date is not None:
                    # Sort by modification date.
                    file_lines.sort(reverse=not sort_by_modified_date, key=lambda x: x[2])
                else:
                    file_lines.sort(
                        reverse=not sort_by_name, key=lambda x: unicode.lower(x[0])
                    )
                lines = [
                    "%-40s  %16s  %24s"
                    % (
                        i[0],
                        "%s bytes" % (i[1],) if i[1] is not None else "",
                        time.strftime("%c", time.localtime(i[2])) if i[2] else "",
                    )
                    for i in file_lines
                ]
                self.view.contents = [i[3] for i in file_lines]
            except OSError as e:
                lines = ["Error opening directory."]
                lines.append(unicode(e))
            clip = ["./", "../"] + lines
        else:
            clip = [dir_path + ": not found"]
        self.view.text_buffer.replace_lines(tuple(clip))
        self.view.text_buffer.parse_screen_maybe()
        self.view.text_buffer.pen_row = 0
        self.view.text_buffer.pen_col = 0
        self.view.text_buffer.goal_col = 0
        self.view.scroll_row = 0
        self.view.scroll_col = 0
        self.filter = None

    def perform_open(self):
        self.open_file_or_dir(self.text_buffer.pen_row)

    def open_file_or_dir(self, row):
        if app.config.strict_debug:
            assert isinstance(row, int)
        path = self.path_for_row(row)
        # Clear the shown directory to trigger a refresh.
        self.shown_directory = None
        self.view.parent.path_window.controller.set_encoded_path(path)
        self.view.host.controller.perform_primary_action()

    def current_directory(self):
        path_controller = self.view.parent.path_window.controller
        path = path_controller.decoded_path()
        if len(path) > 0 and path[-1] != os.path.sep:
            path = os.path.dirname(path)
            # Test that path is non-empty and there's more than just a '/'.
            if len(path) > len(os.path.sep):
                path += os.path.sep
        if app.config.strict_debug:
            assert isinstance(path, unicode)
        return path

    def pass_default_to_path_input(self, ch, meta):
        path_input = self.find_and_change_to("path_window")
        path_input.controller.do_command(ch, meta)

    def path_for_row(self, row):
        if app.config.strict_debug:
            assert isinstance(row, int)
            assert row >= 0, row
        path = self.current_directory()
        if row == 0:
            return path + "./"
        elif row == 1:
            return path + "../"
        return path + self.view.contents[row - 2]

    def option_changed(self, name, value):
        self.shown_directory = None
        self.on_change()

    def set_filter(self, list_filter):
        self.filter = list_filter
        self.shown_directory = None  # Cause a refresh.

class FileManagerController(app.controller.Controller):
    """Create or open files."""

    def __init__(self, view):
        app.controller.Controller.__init__(self, view, "FileManagerController")

    def perform_primary_action(self):
        self.view.path_window.controller.perform_primary_action()

    def info(self):
        app.log.info("FileManagerController command set")

    def on_change(self):
        self.view.directory_list.controller.on_change()
        app.controller.Controller.on_change(self)

    def option_changed(self, name, value):
        self.view.directory_list.controller.shown_directory = None

    def pass_event_to_directory_list(self):
        self.view.directory_list.controller.do_command(self.saved_ch, None)

class FilePathInputController(app.controller.Controller):
    """Manipulate path string."""

    def __init__(self, view):
        app.controller.Controller.__init__(self, view, "FilePathInputController")
        self.primary_actions = {
            "open": self.do_create_or_open,
            "save_as": self.do_save_as,
            "select_dir": self.do_select_dir,
        }

    def perform_primary_action(self):
        path = self.decoded_path()
        if len(path) == 0:
            app.log.info("path is empty")
            return
        if path.endswith("/./"):
            # self.shown_directory = None
            self.set_encoded_path(path[:-2])
            return
        if path.endswith("/../"):
            path = os.path.dirname(path[:-4])
            if len(path) > len(os.path.sep):
                path += os.path.sep
            self.set_encoded_path(path)
            return

        self.primary_actions[self.view.parent.mode]()

    def do_create_or_open(self):
        decoded_path = self.decoded_path()
        if os.path.isdir(decoded_path):
            app.log.info("is dir", repr(decoded_path))
            return
        app_prefs = self.view.program.prefs
        path, open_to_row, open_to_column = app.buffer_file.path_row_column(
            decoded_path, app_prefs.editor["base_dir_env"]
        )
        if not os.access(path, os.R_OK):
            if os.path.isfile(path):
                app.log.info("File not readable.")
                return
        self.set_encoded_path("")
        text_buffer = self.view.program.buffer_manager.load_text_buffer(path)
        if text_buffer is None:
            return
        if open_to_row is not None:
            text_buffer.pen_row = open_to_row if open_to_row > 0 else 0
        if open_to_column is not None:
            text_buffer.pen_col = open_to_column if open_to_column > 0 else 0
            text_buffer.goal_col = text_buffer.pen_col
        # assert text_buffer.parser
        input_window = self.current_input_window()
        input_window.set_text_buffer(text_buffer)
        text_buffer.scroll_to_optimal_scroll_position()
        self.change_to(input_window)

    def do_save_as(self):
        path = self.decoded_path()
        if os.path.isdir(path):
            return
        input_window = self.current_input_window()
        tb = input_window.text_buffer
        tb.set_file_path(path)
        self.change_to(input_window)
        if not len(path):
            tb.set_message("File not saved (file name was empty).")
            return
        if not tb.is_safe_to_write():
            self.view.change_focus_to(input_window.confirm_overwrite)
            return
        tb.file_write()
        self.set_encoded_path("")

    def do_select_dir(self):
        # TODO(dschuyler): not yet implemented.
        self.set_encoded_path("")
        self.change_to_input_window()

    def decoded_path(self):
        if app.config.strict_debug:
            assert self.view.text_buffer is self.text_buffer
        return app.string.path_decode(self.text_buffer.parser.row_text(0))

    def set_encoded_path(self, path):
        if app.config.strict_debug:
            assert isinstance(path, unicode)
            assert self.view.text_buffer is self.text_buffer
        self.text_buffer.replace_lines((app.string.path_encode(path),))
        self.text_buffer.parse_document()

    def info(self):
        app.log.info("FilePathInputController command set")

    def maybe_slash(self, expanded_path):
        # TODO Maybe just get the last character instead.
        line = self.text_buffer.parser.row_text(0)
        if line and line[-1] != "/" and os.path.isdir(expanded_path):
            self.text_buffer.insert("/")

    def on_change(self):
        self.get_named_window("directory_list").controller.on_change()
        app.controller.Controller.on_change(self)

    def option_changed(self, name, value):
        self.get_named_window("directory_list").controller.shown_directory = None

    def pass_event_to_directory_list(self):
        directory_list = self.find_and_change_to("directory_list")
        directory_list.controller.do_command(self.saved_ch, None)

    def tab_complete_extend(self):
        """Extend the selection to match characters in common."""
        decoded_path = self.decoded_path()
        expanded_path = os.path.expandvars(os.path.expanduser(decoded_path))
        dir_path, file_name = os.path.split(expanded_path)
        expanded_dir = dir_path or "."
        matches = []
        if not os.path.isdir(expanded_dir):
            return
        for i in os.listdir(expanded_dir):
            if i.startswith(file_name):
                matches.append(i)
        if len(matches) <= 0:
            self.maybe_slash(expanded_dir)
            self.on_change()
            return
        if len(matches) == 1:
            self.set_encoded_path(decoded_path + matches[0][len(file_name) :])
            self.maybe_slash(os.path.join(expanded_dir, matches[0]))
            self.on_change()
            return

        def find_common_prefix_length(prefix_len):
            count = 0
            ch = None
            for match in matches:
                if len(match) <= prefix_len:
                    return prefix_len
                if not ch:
                    ch = match[prefix_len]
                if match[prefix_len] == ch:
                    count += 1
            if count and count == len(matches):
                return find_common_prefix_length(prefix_len + 1)
            return prefix_len

        prefix_len = find_common_prefix_length(len(file_name))
        self.set_encoded_path(decoded_path + matches[0][len(file_name) : prefix_len])
        if expanded_path == os.path.expandvars(os.path.expanduser(self.decoded_path())):
            # No further expansion found.
            self.get_named_window("directory_list").controller.set_filter(file_name)
        self.on_change()
