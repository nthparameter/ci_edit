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

import app.config
import app.cu_editor
import app.log
import app.text_buffer
import app.window

class PredictionList(app.window.Window):
    """This <tbd>."""

    def __init__(self, program, host):
        if app.config.strict_debug:
            assert host
            assert self is not host
        app.window.Window.__init__(self, program, host)
        self.host = host
        self.is_focusable = False
        self.controller = app.cu_editor.PredictionList(self)
        self.set_text_buffer(app.text_buffer.TextBuffer(self.program))
        # Set up table headers.
        color = host.program.color.get("top_info")
        self.options_row = app.window.OptionsSelectionWindow(self.program, self)
        self.options_row.set_parent(self)
        self.type_column = app.window.SortableHeaderWindow(
            self.program,
            self.options_row,
            "Type",
            "editor",
            "prediction_sort_ascending_by_type",
            8,
        )
        label = app.window.LabelWindow(self.program, self.options_row, "|")
        label.set_parent(self.options_row)
        label.color = color
        self.name_column = app.window.SortableHeaderWindow(
            self.program,
            self.options_row,
            "Name",
            "editor",
            "prediction_sort_ascending_by_name",
            -61,
        )
        label = app.window.LabelWindow(self.program, self.options_row, "|")
        label.set_parent(self.options_row)
        label.color = color
        self.status_column = app.window.SortableHeaderWindow(
            self.program,
            self.options_row,
            "Status ",
            "editor",
            "prediction_sort_ascending_by_status",
            -7,
        )
        label = app.window.LabelWindow(self.program, self.options_row, "|")
        label.set_parent(self.options_row)
        label.color = color

    def highlight_line(self, row):
        self.text_buffer.pen_row = min(row, self.text_buffer.parser.row_count() - 1)
        self.text_buffer.pen_col = 0
        app.log.info(self.text_buffer.pen_row)

    def mouse_click(self, pane_row, pane_col, shift, ctrl, alt):
        self.highlight_line(self.scroll_row + pane_row)
        row = self.scroll_row + pane_row
        if row >= self.text_buffer.parser.row_count():
            return
        self.controller.open_file_or_dir(row)

    def mouse_double_click(self, pane_row, pane_col, shift, ctrl, alt):
        app.log.info()
        assert False

    # def mouse_moved(self, pane_row, pane_col, shift, ctrl, alt):
    #  app.log.info()

    # def mouse_release(self, pane_row, pane_col, shift, ctrl, alt):
    #  app.log.info()

    # def mouse_triple_click(self, pane_row, pane_col, shift, ctrl, alt):
    #  app.log.info()

    def mouse_wheel_down(self, shift, ctrl, alt):
        self.text_buffer.mouse_wheel_down(shift, ctrl, alt)

    def mouse_wheel_up(self, shift, ctrl, alt):
        self.text_buffer.mouse_wheel_up(shift, ctrl, alt)

    def update(self, items):
        # Filter the list. (The filter function is not used so as to edit the
        # list in place).
        app_prefs = self.program.prefs
        show_open = app_prefs.editor["prediction_show_open_files"]
        show_alternate = app_prefs.editor["prediction_show_alternate_files"]
        show_recent = app_prefs.editor["prediction_show_recent_files"]
        if not (show_open and show_alternate and show_recent):
            i = 0
            while i < len(items):
                if not show_open and items[i][3] == "open":
                    items.pop(i)
                elif not show_alternate and items[i][3] == "alt":
                    items.pop(i)
                elif not show_recent and items[i][3] == "recent":
                    items.pop(i)
                else:
                    i += 1
        # Sort the list
        sort_by_prediction = app_prefs.editor["prediction_sort_ascending_by_prediction"]
        sort_by_type = app_prefs.editor["prediction_sort_ascending_by_type"]
        sort_by_name = app_prefs.editor["prediction_sort_ascending_by_name"]
        sort_by_status = app_prefs.editor["prediction_sort_ascending_by_status"]
        if sort_by_prediction is not None:
            items.sort(reverse=not sort_by_prediction, key=lambda x: x[4])
        elif sort_by_type is not None:
            items.sort(reverse=not sort_by_type, key=lambda x: x[3])
        elif sort_by_status is not None:
            items.sort(reverse=not sort_by_status, key=lambda x: x[2])
        elif sort_by_name is not None:
            items.sort(reverse=not sort_by_name, key=lambda x: x[1])
        # Write the lines to the text buffer.
        def fit_path_to_width(path, width):
            if len(path) < width:
                return path
            return path[-width:]

        if len(items) == 0:
            self.text_buffer.replace_lines(("",))
        else:
            self.text_buffer.replace_lines(
                tuple(
                    [
                        "%*s %*s %.*s"
                        % (
                            self.type_column.cols,
                            i[3],
                            -self.name_column.cols,
                            fit_path_to_width(i[1], self.name_column.cols),
                            self.status_column.cols,
                            i[2],
                        )
                        for i in items
                    ]
                )
            )
        self.text_buffer.parse_screen_maybe()  # TODO(dschuyler): Add test.
        self.text_buffer.cursor_move_to_begin()

    def on_pref_changed(self, category, name):
        self.controller.option_changed(category, name)
        app.window.Window.on_pref_changed(self, category, name)

    def reshape(self, top, left, rows, cols):
        """Change self and sub-windows to fit within the given rectangle."""
        app.log.detail("reshape", top, left, rows, cols)
        self.options_row.reshape(top, left, 1, cols)
        top += 1
        rows -= 1
        app.window.Window.reshape(self, top, left, rows, cols)

    def set_text_buffer(self, text_buffer):
        if app.config.strict_debug:
            assert text_buffer is not self.host.text_buffer
        text_buffer.line_limit_indicator = 0
        text_buffer.highlight_cursor_line = True
        text_buffer.highlight_trailing_whitespace = False
        app.window.Window.set_text_buffer(self, text_buffer)
        self.controller.set_text_buffer(text_buffer)

class PredictionInputWindow(app.window.Window):
    def __init__(self, program, host):
        if app.config.strict_debug:
            assert host
            assert issubclass(host.__class__, app.window.ActiveWindow), host
        app.window.Window.__init__(self, program, host)
        self.host = host
        self.controller = app.cu_editor.PredictionInputController(self)
        self.set_text_buffer(app.text_buffer.TextBuffer(self.program))

    def get_path(self):
        return self.text_buffer.parser.row_text(0)

    def set_path(self, path):
        self.text_buffer.replace_lines((path,))

    def set_text_buffer(self, text_buffer):
        text_buffer.line_limit_indicator = 0
        text_buffer.highlight_trailing_whitespace = False
        app.window.Window.set_text_buffer(self, text_buffer)
        self.controller.set_text_buffer(text_buffer)

class PredictionWindow(app.window.Window):
    def __init__(self, program, host):
        app.window.Window.__init__(self, program, host)

        self.show_tips = False
        self.controller = app.cu_editor.PredictionController(self)
        self.set_text_buffer(app.text_buffer.TextBuffer(self.program))

        self.title_row = app.window.OptionsRow(self.program, self)
        self.title_row.add_label(" ci   ")
        self.title_row.set_parent(self)

        self.prediction_input_window = PredictionInputWindow(self.program, self)
        self.prediction_input_window.set_parent(self)

        self.prediction_list = PredictionList(self.program, self)
        self.prediction_list.set_parent(self)

        if 1:
            self.options_row = app.window.RowWindow(self.program, self, 2)
            self.options_row.set_parent(self)
            colorPrefs = host.program.color
            self.options_row.color = colorPrefs.get("top_info")
            label = app.window.LabelWindow(self.program, self.options_row, "Show:")
            label.color = colorPrefs.get("top_info")
            label.set_parent(self.options_row)
            toggle = app.window.OptionsToggle(
                self.program,
                self.options_row,
                "open",
                "editor",
                "prediction_show_open_files",
            )
            toggle.color = colorPrefs.get("top_info")
            toggle = app.window.OptionsToggle(
                self.program,
                self.options_row,
                "alternates",
                "editor",
                "prediction_show_alternate_files",
            )
            toggle.color = colorPrefs.get("top_info")
            toggle = app.window.OptionsToggle(
                self.program,
                self.options_row,
                "recent",
                "editor",
                "prediction_show_recent_files",
            )
            toggle.color = colorPrefs.get("top_info")

        self.messageLine = app.window.LabelWindow(self.program, self, "")
        self.messageLine.set_parent(self)

    def bring_child_to_front(self, child):
        # The PredictionWindow window doesn't reorder children.
        pass

    def focus(self):
        self.reattach()
        self.parent.layout()
        app.window.Window.focus(self)
        self.change_focus_to(self.prediction_input_window)

    def get_path(self):
        return self.prediction_input_window.get_path()

    def on_pref_changed(self, category, name):
        self.prediction_list.controller.option_changed(category, name)
        app.window.Window.on_pref_changed(self, category, name)

    def reshape(self, top, left, rows, cols):
        """Change self and sub-windows to fit within the given rectangle."""
        app.window.Window.reshape(self, top, left, rows, cols)
        self.title_row.reshape(top, left, 1, cols)
        top += 1
        rows -= 1
        self.prediction_input_window.reshape(top, left, 1, cols)
        top += 1
        rows -= 1
        self.messageLine.reshape(top + rows - 1, left, 1, cols)
        rows -= 1
        self.options_row.reshape(top + rows - 1, left, 1, cols)
        rows -= 1
        self.prediction_list.reshape(top, left, rows, cols)

    def set_path(self, path):
        self.prediction_input_window.set_path(path)

    def unfocus(self):
        app.window.Window.unfocus(self)
        self.detach()
