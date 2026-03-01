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

try:
    unicode
except NameError:
    unicode = str
    unichr = chr

import bisect
import os
import sys
import types
import curses

import app.config
import app.controller
import app.cu_editor
import app.em_editor
import app.string
import app.text_buffer
import app.vi_editor

# The terminal area that the curses can draw to.
main_curses_window = None

class ViewWindow:
    """A view window is a base window that does not get focus or have
    TextBuffer.

    See class ActiveWindow for a window that can get focus. See class Window for
    a window that can get focus and have a TextBuffer.
    """

    def __init__(self, program, parent):
        """
        Args:
          parent is responsible for the order in which this window is updated,
          relative to its siblings.
        """
        if app.config.strict_debug:
            assert issubclass(self.__class__, ViewWindow), self
            assert issubclass(program.__class__, app.ci_program.CiProgram), self
            if parent is not None:
                assert issubclass(parent.__class__, ViewWindow), parent
        self.program = program
        self.parent = parent
        self.is_focusable = False
        self.top = 0
        self.left = 0
        self.rows = 1
        self.cols = 1
        self.scroll_row = 0
        self.scroll_col = 0
        self.show_cursor = True
        self.writeLineRow = 0
        self.z_order = []

    def add_str(self, row, col, text, color_pair):
        """Overwrite text at row, column with text.

        The caller is responsible for avoiding overdraw.
        """
        if app.config.strict_debug:
            app.log.check_le(row, self.rows)
            app.log.check_le(col, self.cols)
        self.program.background_frame.add_str(
            self.top + row, self.left + col, text.encode("utf-8"), color_pair
        )

    def reattach(self):
        self.set_parent(self.parent)

    def blank(self, color_pair):
        """Clear the window."""
        for i in range(self.rows):
            self.add_str(i, 0, " " * self.cols, color_pair)

    def bring_child_to_front(self, child):
        """Bring it to the top layer."""
        try:
            self.z_order.remove(child)
        except ValueError:
            pass
        self.z_order.append(child)

    def bring_to_front(self):
        """Bring it to the top layer."""
        self.parent.bring_child_to_front(self)

    def change_focus_to(self, change_to):
        if app.config.strict_debug:
            assert issubclass(self.__class__, ViewWindow), self
            assert issubclass(change_to.__class__, ViewWindow), change_to
        top_window = self
        while top_window.parent:
            top_window = top_window.parent
        top_window.change_focus_to(change_to)

    def color_pref(self, color_type, delta=0):
        return self.program.color.get(color_type, delta)

    def contains(self, row, col):
        """Determine whether the position at row, col lay within this window."""
        for i in self.z_order:
            if i.contains(row, col):
                return i
        return (
            self.top <= row < self.top + self.rows
            and self.left <= col < self.left + self.cols
            and self
        )

    def debug_draw(self):
        program_window = self
        while program_window.parent is not None:
            program_window = program_window.parent
        program_window.debug_draw(self)

    def deselect(self):
        pass

    def detach(self):
        """Hide the window by removing self from parents' children, but keep
        same parent to be reattached later."""
        try:
            self.parent.z_order.remove(self)
        except ValueError:
            pass

    def layout_horizontally(self, children, separation=0):
        left = self.left
        cols = self.cols
        for view in children:
            preferred_cols = view.preferred_size(self.rows, max(0, cols))[1]
            view.reshape(self.top, left, self.rows, max(0, min(cols, preferred_cols)))
            delta = view.cols + separation
            left += delta
            cols -= delta

    def layout_vertically(self, children, separation=0):
        top = self.top
        rows = self.rows
        for view in children:
            preferred_rows = view.preferred_size(max(0, rows), self.cols)[0]
            view.reshape(top, self.left, max(0, min(rows, preferred_rows)), self.cols)
            delta = view.rows + separation
            top += delta
            rows -= delta

    def mouse_click(self, pane_row, pane_col, shift, ctrl, alt):
        pass

    def mouse_double_click(self, pane_row, pane_col, shift, ctrl, alt):
        pass

    def mouse_moved(self, pane_row, pane_col, shift, ctrl, alt):
        pass

    def mouse_release(self, pane_row, pane_col, shift, ctrl, alt):
        pass

    def mouse_triple_click(self, pane_row, pane_col, shift, ctrl, alt):
        pass

    def mouse_wheel_down(self, shift, ctrl, alt):
        pass

    def mouse_wheel_up(self, shift, ctrl, alt):
        pass

    def move_to(self, top, left):
        self.top = top
        self.left = left

    def move_by(self, top, left):
        self.top += top
        self.left += left

    def _child_focusable_window(self, reverse=False):
        windows = self.z_order[:]
        if reverse:
            windows.reverse()
        for i in windows:
            if i.is_focusable:
                return i
            else:
                r = i._child_focusable_window(reverse)
                if r is not None:
                    return r

    def next_focusable_window(self, start, reverse=False):
        """Windows without |is_focusable| are skipped. Ignore (skip) |start| when
        searching.

        Args:
          start (window): the child window to start from. If |start| is not
              found, start from the first child window.
          reverse (bool): if True, find the prior focusable window.

        Returns:
          A window that should be focused.

        See also: show_full_window_hierarchy() which can help in debugging.
        """
        windows = self.parent.z_order[:]
        if reverse:
            windows.reverse()
        try:
            found = windows.index(start)
        except ValueError:
            found = -1
        windows = windows[found + 1 :]
        for i in windows:
            if i.is_focusable:
                return i
            else:
                r = i._child_focusable_window(reverse)
                if r is not None:
                    return r
        r = self.parent.next_focusable_window(self.parent, reverse)
        if r is not None:
            return r
        return self._child_focusable_window(reverse)

    def normalize(self):
        self.parent.normalize()

    def on_pref_changed(self, category, name):
        self.parent.on_pref_changed(category, name)

    def paint(self, row, col, count, color_pair):
        """Paint text a row, column with color_pair.

        fyi, I thought this may be faster than using add_str to paint over the
        text with a different color_pair. It looks like there isn't a significant
        performance difference between chgat and addstr.
        """
        main_curses_window.chgat(self.top + row, self.left + col, count, color_pair)

    def preferred_size(self, row_limit, col_limit):
        # Derived classes should override this.
        return row_limit, col_limit

    def present_modal(self, change_to, pane_row, pane_col):
        self.parent.present_modal(change_to, pane_row, pane_col)

    def prior_focusable_window(self, start):
        return self.next_focusable_window(start, True)

    def quit_now(self):
        self.program.quit_now()

    def render(self):
        """Redraw window."""
        for child in self.z_order:
            child.render()

    def show_window_hierarchy(self, indent="  "):
        """For debugging."""
        focus = "[f]" if self.is_focusable else "[ ]"
        extra = ""
        if hasattr(self, "label"):
            extra += ' "' + self.label + '"'
        app.log.info(f"{indent}{focus}{self}{extra}")
        for child in self.z_order:
            child.show_window_hierarchy(indent + "  ")

    def show_full_window_hierarchy(self, indent="  "):
        """For debugging."""
        f = self
        while f.parent is not None:
            f = f.parent
        assert f
        f.show_window_hierarchy()

    def do_pre_command(self):
        pass

    def long_time_slice(self):
        """returns whether work is finished (no need to call again)."""
        return True

    def short_time_slice(self):
        """returns whether work is finished (no need to call again)."""
        return True

    def reshape(self, top, left, rows, cols):
        self.move_to(top, left)
        self.resize_to(rows, cols)
        # app.log.debug(self, top, left, rows, cols)

    def resize_bottom_by(self, rows):
        self.rows += rows

    def resize_by(self, rows, cols):
        self.rows += rows
        self.cols += cols

    def resize_to(self, rows, cols):
        # app.log.detail(rows, cols, self)
        if app.config.strict_debug:
            assert rows >= 0, rows
            assert cols >= 0, cols
        self.rows = rows
        self.cols = cols

    def resize_top_by(self, rows):
        self.top += rows
        self.rows -= rows

    def set_parent(self, parent, layer_index=sys.maxsize):
        """Setting the parent will cause the the window to refresh (i.e. if self
        was hidden with detach() it will no longer be hidden)."""
        if app.config.strict_debug:
            assert issubclass(self.__class__, ViewWindow), self
            assert issubclass(parent.__class__, ViewWindow), parent
        if self.parent:
            try:
                self.parent.z_order.remove(self)
            except ValueError:
                pass
        self.parent = parent
        if parent:
            self.parent.z_order.insert(layer_index, self)

    def write_line(self, text, color):
        """Simple line writer for static windows."""
        if app.config.strict_debug:
            assert isinstance(text, unicode)
        text = text[: self.cols]
        text = text + " " * max(0, self.cols - len(text))
        self.program.background_frame.add_str(
            self.top + self.writeLineRow, self.left, text.encode("utf-8"), color
        )
        self.writeLineRow += 1

    def get_program(self):
        return self.program

class ActiveWindow(ViewWindow):
    """An ActiveWindow may have focus and a controller."""

    def __init__(self, program, parent):
        if app.config.strict_debug:
            assert issubclass(self.__class__, ActiveWindow), self
            assert issubclass(program.__class__, app.ci_program.CiProgram), repr(
                program
            )
            if parent is not None:
                assert issubclass(parent.__class__, ViewWindow), parent
        ViewWindow.__init__(self, program, parent)
        self.controller = None
        self.has_focus = False
        self.is_focusable = True

    def focus(self):
        """
        Note: to focus a view it must have a controller. Focusing a view without
            a controller would make the program appear to freeze since nothing
            would be responding to user input.
        """
        self.has_focus = True
        self.controller.focus()

    def set_controller(self, controller):
        if app.config.strict_debug:
            assert issubclass(self.__class__, Window), self
        self.controller = controller(self)

    def unfocus(self):
        self.has_focus = False
        self.controller.unfocus()

class Window(ActiveWindow):
    """A Window holds a TextBuffer and a controller that operates on the
    TextBuffer."""

    def __init__(self, program, parent):
        if app.config.strict_debug:
            assert issubclass(self.__class__, Window), self
            assert issubclass(program.__class__, app.ci_program.CiProgram), self
            assert issubclass(parent.__class__, ViewWindow), parent
        ActiveWindow.__init__(self, program, parent)
        self.has_captive_cursor = self.program.prefs.editor["captive_cursor"]
        self.text_buffer = None

    def mouse_click(self, pane_row, pane_col, shift, ctrl, alt):
        if self.text_buffer:
            self.text_buffer.mouse_click(pane_row, pane_col, shift, ctrl, alt)

    def mouse_double_click(self, pane_row, pane_col, shift, ctrl, alt):
        if self.text_buffer:
            self.text_buffer.mouse_double_click(pane_row, pane_col, shift, ctrl, alt)

    def mouse_moved(self, pane_row, pane_col, shift, ctrl, alt):
        if self.text_buffer:
            self.text_buffer.mouse_moved(pane_row, pane_col, shift, ctrl, alt)

    def mouse_release(self, pane_row, pane_col, shift, ctrl, alt):
        if self.text_buffer:
            self.text_buffer.mouse_release(pane_row, pane_col, shift, ctrl, alt)

    def mouse_triple_click(self, pane_row, pane_col, shift, ctrl, alt):
        if self.text_buffer:
            self.text_buffer.mouse_triple_click(pane_row, pane_col, shift, ctrl, alt)

    def mouse_wheel_down(self, shift, ctrl, alt):
        if self.text_buffer:
            self.text_buffer.mouse_wheel_down(shift, ctrl, alt)

    def mouse_wheel_up(self, shift, ctrl, alt):
        if self.text_buffer:
            self.text_buffer.mouse_wheel_up(shift, ctrl, alt)

    def preferred_size(self, row_limit, col_limit):
        return min(row_limit, self.text_buffer.parser.row_count()), col_limit

    def render(self):
        if self.text_buffer:
            self.text_buffer.draw(self)
        ViewWindow.render(self)

    def set_controller(self, controller):
        ActiveWindow.set_controller(self, controller)
        self.controller.set_text_buffer(self.text_buffer)

    def set_text_buffer(self, text_buffer):
        text_buffer.set_view(self)
        self.text_buffer = text_buffer

    def do_pre_command(self):
        if self.text_buffer is not None:
            self.text_buffer.set_message()

    def long_time_slice(self):
        """returns whether work is finished (no need to call again)."""
        finished = True
        tb = self.text_buffer
        if tb is not None and tb.parser.resume_at_row < tb.parser.row_count():
            tb.parse_document()
            # If a user event came in while parsing, the parsing will be paused
            # (to be resumed after handling the event).
            finished = tb.parser.resume_at_row >= tb.parser.row_count()
        for child in self.z_order:
            finished = finished and child.long_time_slice()
        return finished

    def short_time_slice(self):
        """returns whether work is finished (no need to call again)."""
        tb = self.text_buffer
        if tb is not None:
            tb.parse_screen_maybe()
            return tb.parser.resume_at_row >= tb.parser.row_count()
        return True

class LabelWindow(ViewWindow):
    """A text label.

    The label is inert, it will pass events to its parent.
    """

    def __init__(self, program, parent, label, preferred_width=None, align="left"):
        if app.config.strict_debug:
            assert issubclass(program.__class__, app.ci_program.CiProgram), self
            assert issubclass(parent.__class__, ViewWindow), parent
            assert isinstance(label, unicode)
            assert preferred_width is None or isinstance(preferred_width, int)
            assert isinstance(align, unicode)
        ViewWindow.__init__(self, program, parent)
        self.label = label
        self.preferred_width = preferred_width
        self.align = -1 if align == "left" else 1
        self.color = self.program.color.get("keyword")

    def preferred_size(self, row_limit, col_limit):
        if app.config.strict_debug:
            assert self.parent
            assert row_limit >= 0
            assert col_limit >= 0
        preferred_width = (
            self.preferred_width if self.preferred_width is not None else len(self.label)
        )
        return (min(row_limit, 1), min(col_limit, preferred_width))

    def render(self):
        if self.rows <= 0:
            return
        line = self.label[: self.cols]
        line = "%*s" % (self.cols * self.align, line)
        self.add_str(0, 0, line, self.color)
        ViewWindow.render(self)

class LabeledLine(Window):
    """A single line with a label.

    This is akin to a line prompt or gui modal dialog. It's used for things like
    'find' and 'goto line'.
    """

    def __init__(self, program, parent, label):
        if app.config.strict_debug:
            assert issubclass(self.__class__, LabeledLine), self
            assert issubclass(program.__class__, app.ci_program.CiProgram), self
            assert issubclass(parent.__class__, ViewWindow), parent
        Window.__init__(self, program, parent)
        self.host = parent
        tb = app.text_buffer.TextBuffer(self.program)
        tb.root_grammar = self.program.prefs.grammars["none"]
        self.set_text_buffer(tb)
        self.label = label
        self.left_column = ViewWindow(self.program, self)
        # TODO(dschuyler) Add self.right_column.

    def focus(self):
        self.bring_to_front()
        if not self.controller:
            app.log.info(self, repr(self.label))
        Window.focus(self)

    def preferred_size(self, row_limit, col_limit):
        return min(row_limit, 1), col_limit

    def render(self):
        # app.log.info('LabeledLine', self.label, self.rows, self.cols)
        if self.rows <= 0:
            return
        self.left_column.add_str(0, 0, self.label, self.program.color.get("keyword"))
        Window.render(self)

    def reshape(self, top, left, rows, cols):
        label_width = len(self.label)
        Window.reshape(self, top, left + label_width, rows, max(0, cols - label_width))
        self.left_column.reshape(top, left, rows, label_width)

    def set_label(self, label):
        self.label = label
        self.reshape(self.top, self.left, self.rows, self.cols)

class Menu(ViewWindow):
    """Work in progress on a context menu."""

    def __init__(self, program, host):
        if app.config.strict_debug:
            assert issubclass(self.__class__, Menu), self
            assert issubclass(host.__class__, ActiveWindow)
        ViewWindow.__init__(self, program, host)
        self.host = host
        self.label = ""
        self.lines = []
        self.commands = []

    def add_item(self, label, command):
        self.lines.append(label)
        self.commands.append(command)

    def clear(self):
        self.lines = []
        self.commands = []

    def move_size_to_fit(self, left, top):
        self.clear()
        self.add_item("some menu", None)
        # self.add_item('sort', self.host.text_buffer.sortSelection)
        self.add_item("cut", self.host.text_buffer.edit_cut)
        self.add_item("paste", self.host.text_buffer.edit_paste)
        longest = 0
        for i in self.lines:
            if len(i) > longest:
                longest = len(i)
        self.reshape(left, top, len(self.lines), longest + 2)

    def render(self):
        color = self.program.color.get("context_menu")
        self.writeLineRow = 0
        for i in self.lines[: self.rows]:
            self.write_line(" " + i, color)
        ViewWindow.render(self)

class LineNumbers(ViewWindow):
    def __init__(self, program, host):
        ViewWindow.__init__(self, program, host)
        self.host = host

    def draw_line_numbers(self):
        if app.config.strict_debug:
            assert isinstance(self.rows, int)
            assert isinstance(self.host.scroll_row, int)
            assert self.rows >= 1
            assert self.host.text_buffer.parser.row_count() >= 1
            assert self.host.scroll_row >= 0
        limit = min(
            self.rows, self.host.text_buffer.parser.row_count() - self.host.scroll_row
        )
        cursor_bookmark_color_index = None
        visible_bookmarks = self.get_visible_bookmarks(
            self.host.scroll_row, self.host.scroll_row + limit
        )
        current_bookmark_index = 0
        colorPrefs = self.program.color
        for i in range(limit):
            color = colorPrefs.get("line_number")
            current_row = self.host.scroll_row + i
            if current_bookmark_index < len(visible_bookmarks):
                current_bookmark = visible_bookmarks[current_bookmark_index]
            else:
                current_bookmark = None
            # Use a different color if the row is associated with a bookmark.
            if current_bookmark:
                if (
                    current_row >= current_bookmark.begin
                    and current_row <= current_bookmark.end
                ):
                    color = colorPrefs.get(current_bookmark.data.get("color_index"))
                    if self.host.text_buffer.pen_row == current_row:
                        cursor_bookmark_color_index = current_bookmark.data.get(
                            "color_index"
                        )
                if current_row + 1 > current_bookmark.end:
                    current_bookmark_index += 1
            self.add_str(i, 0, f" {current_row + 1:5d} ", color)
        # Draw indicators for text off of the left edge.
        if self.host.scroll_col > 0:
            color = colorPrefs.get("line_overflow")
            for i in range(limit):
                if self.host.text_buffer.parser.row_width(self.host.scroll_row + i) > 0:
                    self.add_str(i, 6, " ", color)
        # Draw blank line number rows past the end of the document.
        color = colorPrefs.get("outside_document")
        for i in range(limit, self.rows):
            self.add_str(i, 0, "       ", color)
        # Highlight the line numbers for the current cursor line.
        cursor_at = self.host.text_buffer.pen_row - self.host.scroll_row
        if 0 <= cursor_at < limit:
            if cursor_bookmark_color_index:
                if self.program.prefs.startup["num_colors"] == 8:
                    color = colorPrefs.get(cursor_bookmark_color_index)
                else:
                    color = colorPrefs.get(cursor_bookmark_color_index % 32 + 128)
            else:
                color = colorPrefs.get("line_number_current")
            self.add_str(cursor_at, 1, f"{self.host.text_buffer.pen_row + 1:5d}", color)

    def get_visible_bookmarks(self, begin_row, end_row):
        """
        Args:
          begin_row (int): the index of the line number that you want the list of
                          bookmarks to start from.
          end_row (int): the index of the line number that you want the list of
                        bookmarks to end at (exclusive).

        Returns:
          A list containing the bookmarks that are displayed on the screen. If
          there are no bookmarks, returns an empty list.
        """
        bookmark_list = self.host.text_buffer.bookmarks
        begin_index = end_index = 0
        if len(bookmark_list):
            needle = app.bookmark.Bookmark(begin_row, begin_row, {})
            begin_index = bisect.bisect_left(bookmark_list, needle)
            if begin_index > 0 and bookmark_list[begin_index - 1].end >= begin_row:
                begin_index -= 1
            needle.range = (end_row, end_row)
            end_index = bisect.bisect_left(bookmark_list, needle)
        return bookmark_list[begin_index:end_index]

    def mouse_click(self, pane_row, pane_col, shift, ctrl, alt):
        if ctrl:
            app.log.info("click at", pane_row, pane_col)
            return
        self.host.change_focus_to(self.host)
        tb = self.host.text_buffer
        if self.host.scroll_row + pane_row >= tb.parser.row_count():
            tb.selection_none()
            return
        if shift:
            if tb.selection_mode == app.selectable.SELECTION_NONE:
                tb.selection_line()
            self.mouse_release(pane_row, pane_col, shift, ctrl, alt)
        else:
            tb.cursor_move_and_mark(
                self.host.scroll_row + pane_row - tb.pen_row,
                0,
                self.host.scroll_row + pane_row - tb.marker_row,
                0,
                app.selectable.SELECTION_NONE - tb.selection_mode,
            )
            self.mouse_release(pane_row, pane_col, shift, ctrl, alt)

    def mouse_double_click(self, pane_row, pane_col, shift, ctrl, alt):
        self.host.text_buffer.selection_all()

    def mouse_moved(self, pane_row, pane_col, shift, ctrl, alt):
        app.log.info(pane_row, pane_col, shift)
        self.host.text_buffer.mouse_moved(pane_row, pane_col - self.cols, True, ctrl, alt)

    def mouse_release(self, pane_row, pane_col, shift, ctrl, alt):
        app.log.info(pane_row, pane_col, shift)
        tb = self.host.text_buffer
        tb.select_line_at(self.host.scroll_row + pane_row)

    def mouse_triple_click(self, pane_row, pane_col, shift, ctrl, alt):
        pass

    def mouse_wheel_down(self, shift, ctrl, alt):
        self.host.mouse_wheel_down(shift, ctrl, alt)

    def mouse_wheel_up(self, shift, ctrl, alt):
        self.host.mouse_wheel_up(shift, ctrl, alt)

    def render(self):
        self.draw_line_numbers()

class LogWindow(ViewWindow):
    def __init__(self, program, parent):
        ViewWindow.__init__(self, program, parent)
        self.lines = app.log.get_lines()
        self.render_counter = 0

    def render(self):
        self.render_counter += 1
        app.log.meta(" " * 10, self.render_counter, "- screen render -")
        self.writeLineRow = 0
        colorPrefs = self.program.color
        color_a = colorPrefs.get("default")
        color_b = colorPrefs.get("highlight")
        for i in self.lines[-self.rows :]:
            color = color_a
            if len(i) and i[-1] == "-":
                color = color_b
            self.write_line(i, color)
        ViewWindow.render(self)

class InteractiveFind(Window):
    def __init__(self, program, host):
        Window.__init__(self, program, host)
        self.host = host
        self.expanded = False
        self.set_controller(app.cu_editor.InteractiveFind)
        indent = "  "

        self.find_line = LabeledLine(self.program, self, "Find: ")
        self.find_line.set_controller(app.cu_editor.InteractiveFindInput)
        self.find_line.set_parent(self)

        self.replace_line = LabeledLine(self.program, self, "Replace: ")
        self.replace_line.set_controller(app.cu_editor.InteractiveReplaceInput)
        self.replace_line.set_parent(self)

        self.match_options_row = RowWindow(self.program, self, 2)
        self.match_options_row.set_parent(self)

        # If find_use_regex is false, re.escape the search.
        OptionsToggle(
            self.program, self.match_options_row, "regex", "editor", "find_use_regex"
        )
        # If find_whole_word, wrap with \b.
        OptionsToggle(
            self.program,
            self.match_options_row,
            "wholeWord",
            "editor",
            "find_whole_word",
        )
        # If find_ignore_case, pass ignore case flag to regex.
        OptionsToggle(
            self.program,
            self.match_options_row,
            "ignoreCase",
            "editor",
            "find_ignore_case",
        )
        if 0:
            # Use locale.
            OptionsToggle(
                self.program, self.match_options_row, "locale", "editor", "find_locale"
            )
            # Span lines.
            OptionsToggle(
                self.program,
                self.match_options_row,
                "multiline",
                "editor",
                "find_multiline",
            )
            # Dot matches anything (even \n).
            OptionsToggle(
                self.program, self.match_options_row, "dotAll", "editor", "find_dot_all"
            )
            # Unicode match.
            OptionsToggle(
                self.program,
                self.match_options_row,
                "unicode",
                "editor",
                "find_unicode",
            )
            # Replace uppercase with upper and lowercase with lower.
            OptionsToggle(
                self.program,
                self.match_options_row,
                "smartCaps",
                "editor",
                "findReplaceSmartCaps",
            )

        if 0:
            self.scopeOptions, self.scopeRow = self.add_select_options_row(
                indent + "scope     ",
                ["file", "directory", "openFiles", "project"],
            )
            (self.changeCaseOptions, self.changeCaseRow) = self.add_select_options_row(
                indent + "changeCase", ["none", "smart", "upper", "lower"]
            )
            (self.withinOptions, self.withinOptionsRow) = self.add_select_options_row(
                indent + "within    ",
                [
                    "any",
                    "code",
                    "comment",
                    "error",
                    "markup",
                    "misspelled",  # Find in misspelled words.
                    "quoted",  # Find in strings.
                ],
            )
            (
                self.searchSelectionOption,
                self.searchSelectionRow,
            ) = self.add_select_options_row(
                indent + "selection ", ["any", "yes", "no"]
            )
            (
                self.searchChangedOption,
                self.searchChangedRow,
            ) = self.add_select_options_row(
                indent + "changed   ", ["any", "yes", "no"]
            )
            self.paths_line = LabeledLine(self.program, self, "Paths: ")
            self.paths_line.set_controller(app.cu_editor.InteractiveFindInput)
            self.paths_line.set_parent(self)

    def reattach(self):
        Window.reattach(self)
        # TODO(dschuyler): consider removing expanded control.
        # See https://github.com/google/ci_edit/issues/170
        self.expanded = True
        self.parent.layout()

    def detach(self):
        Window.detach(self)
        self.parent.layout()

    def add_select_options_row(self, label, options_list):
        """Such as a radio group."""
        options_row = OptionsRow(self.program, self)
        options_row.color = self.program.color.get("keyword")
        options_row.add_label(label)
        options_dict = {}
        options_row.begin_group()
        for key in options_list:
            options_dict[key] = False
            options_row.add_selection(key, options_dict)
        options_row.end_group()
        options_dict[options_list[0]] = True
        options_row.set_parent(self)
        return options_dict, options_row

    def bring_child_to_front(self, child):
        # The find window doesn't reorder children.
        pass

    def focus(self):
        self.reattach()
        if app.config.strict_debug:
            assert self.parent
            assert self.find_line.parent
            assert self.rows > 0, self.rows
            assert self.find_line.rows > 0, self.find_line.rows
        self.controller.focus()
        self.change_focus_to(self.find_line)

    def preferred_size(self, row_limit, col_limit):
        if app.config.strict_debug:
            assert self.parent
            assert row_limit >= 0
            assert col_limit >= 0
        if self.parent and self in self.parent.z_order and self.expanded:
            return (min(row_limit, len(self.z_order)), col_limit)
        return (1, -1)

    def expand_find_window(self, expanded):
        self.expanded = expanded
        self.parent.layout()

    def reshape(self, top, left, rows, cols):
        Window.reshape(self, top, left, rows, cols)
        self.layout_vertically(self.z_order)

    def unfocus(self):
        self.detach()
        Window.unfocus(self)

class MessageLine(ViewWindow):
    """The message line appears at the bottom of the screen."""

    def __init__(self, program, host):
        ViewWindow.__init__(self, program, host)
        self.host = host
        self.message = None
        self.rendered_message = None

    def render(self):
        colorPrefs = self.program.color
        if self.message:
            if self.message != self.rendered_message:
                self.writeLineRow = 0
                self.write_line(self.message, colorPrefs.get("message_line"))
        else:
            self.blank(colorPrefs.get("message_line"))

class StatusLine(ViewWindow):
    """The status line appears at the bottom of the screen.

    It shows the current line and column the cursor is on.
    """

    def __init__(self, program, host):
        ViewWindow.__init__(self, program, host)
        self.host = host

    def render(self):
        tb = self.host.text_buffer
        colorPrefs = self.program.color
        color = colorPrefs.get("status_line")
        if self.host.show_tips:
            tip_rows = app.help.docs["tips"]
            if len(tip_rows) + 1 < self.rows:
                for i in range(self.rows):
                    self.add_str(i, 0, " " * self.cols, color)
                for i, k in enumerate(tip_rows):
                    self.add_str(i + 1, 4, k, color)
                self.add_str(
                    1, 40, "(Press F1 to show/hide tips)", color | curses.A_REVERSE
                )

        status_line = ""
        if tb.message:
            status_line = tb.message[0]
            color = (
                tb.message[1]
                if tb.message[1] is not None
                else colorPrefs.get("status_line")
            )
        if 0:
            if tb.is_dirty():
                status_line += " * "
            else:
                status_line += " . "
        # Percentages.
        row_percentage = 0
        col_percentage = 0
        line_count = tb.parser.row_count()
        if line_count:
            row_percentage = self.host.text_buffer.pen_row * 100 // line_count
            char_count = tb.parser.row_width(self.host.text_buffer.pen_row)
            if char_count and self.host.text_buffer.pen_col != 0:
                col_percentage = self.host.text_buffer.pen_col * 100 // char_count
        # Format.
        right_side = ""
        if len(status_line):
            right_side += " |"
        if self.program.prefs.startup.get("show_log_window"):
            right_side += f" {tb.cursor_grammar_name()} | {tb.selection_mode_name()} |"
        tb = self.host.text_buffer
        right_side += f" {tb.pen_row + 1:4d},{tb.pen_col + 1:2d} | {row_percentage:3d}%,{col_percentage:3d}%"
        status_line += " " * (self.cols - len(status_line) - len(right_side)) + right_side
        self.add_str(self.rows - 1, 0, status_line[: self.cols], color)

class TopInfo(ViewWindow):
    def __init__(self, program, host):
        ViewWindow.__init__(self, program, host)
        self.host = host
        self.borrowed_rows = 0
        self.lines = []
        self.mode = 2

    def on_change(self):
        if self.mode == 0:
            return
        tb = self.host.text_buffer
        lines = []
        # TODO: Make dynamic topInfo work properly
        if tb.parser.row_count():
            line_cursor = self.host.scroll_row
            line = ""
            # Check for extremely small window.
            if tb.parser.row_count() > line_cursor:
                while len(line) == 0 and line_cursor > 0:
                    line = tb.parser.row_text(line_cursor)
                    line_cursor -= 1
            if len(line):
                indent = len(line) - len(line.lstrip(" "))
                line_cursor += 1
                while line_cursor < tb.parser.row_count():
                    line = tb.parser.row_text(line_cursor)
                    if not len(line):
                        continue
                    z = len(line) - len(line.lstrip(" "))
                    if z > indent:
                        indent = z
                        line_cursor += 1
                    else:
                        break
                while indent and line_cursor > 0:
                    line = tb.parser.row_text(line_cursor)
                    if len(line):
                        z = len(line) - len(line.lstrip(" "))
                        if z < indent:
                            indent = z
                            lines.append(line)
                    line_cursor -= 1
        path_line = app.string.path_encode(self.host.text_buffer.full_path)
        if 1:
            if tb.is_read_only:
                path_line += " [RO]"
        if 1:
            if tb.is_dirty():
                path_line += " * "
            else:
                path_line += " . "
        lines.append(path_line[-self.cols :])
        self.lines = lines
        info_rows = len(self.lines)
        if self.mode > 0:
            info_rows = self.mode
        if self.borrowed_rows != info_rows:
            self.host.top_rows = info_rows
            self.host.layout()
            self.borrowed_rows = info_rows

    def render(self):
        """Render the context information at the top of the window."""
        lines = self.lines[-self.mode :]
        lines.reverse()
        color = self.program.color.get("top_info")
        for i, line in enumerate(lines):
            self.add_str(
                i, 0, (line + " " * (self.cols - len(line)))[: self.cols], color
            )
        for i in range(len(lines), self.rows):
            self.add_str(i, 0, " " * self.cols, color)

    def reshape(self, top, left, rows, cols):
        self.borrowed_rows = 0
        ViewWindow.reshape(self, top, left, rows, cols)

class InputWindow(Window):
    """This is the main content window.

    Often the largest pane displayed.
    """

    def __init__(self, program, host):
        if app.config.strict_debug:
            assert host
        Window.__init__(self, program, host)
        self.host = host
        self.show_footer = True
        self.saved_scroll_positions = {}
        self.show_line_numbers = self.program.prefs.editor.get("show_line_numbers", True)
        self.show_message_line = True
        self.show_right_column = True
        self.show_top_info = True
        self.status_line_count = 0 if self.program.prefs.status.get("seenTips") else 8

        self.top_rows = 2  # Number of lines in default TopInfo status.
        self.controller = app.controller.MainController(self)
        self.controller.add(app.em_editor.EmacsEdit(self))
        self.controller.add(app.vi_editor.ViEdit(self))
        self.controller.add(app.cu_editor.CuaPlusEdit(self))
        # What does the user appear to want: edit, quit, or something else?
        self.user_intent = "edit"
        if 1:
            self.confirm_close = LabeledLine(
                self.program, self, "Save changes? (yes, no, or cancel): "
            )
            self.confirm_close.set_controller(app.cu_editor.ConfirmClose)
        if 1:
            self.confirm_overwrite = LabeledLine(
                self.program, self, "Overwrite exiting file? (yes or no): "
            )
            self.confirm_overwrite.set_controller(app.cu_editor.ConfirmOverwrite)
        self.context_menu = Menu(self.program, self)
        if 1:  # wip on multi-line interactive find.
            self.interactive_find = InteractiveFind(self.program, self)
            self.interactive_find.set_parent(self, 0)
        else:
            self.interactive_find = LabeledLine(self.program, self, "find: ")
            self.interactive_find.set_controller(app.cu_editor.InteractiveFind)
        if 1:
            self.interactive_goto = LabeledLine(self.program, self, "goto: ")
            self.interactive_goto.set_controller(app.cu_editor.InteractiveGoto)
        if 1:
            self.interactive_prediction = LabeledLine(self.program, self, "p: ")
            self.interactive_prediction.set_controller(
                app.cu_editor.InteractivePrediction
            )
        if 1:
            self.interactive_prompt = LabeledLine(self.program, self, "e: ")
            self.interactive_prompt.set_controller(app.cu_editor.InteractivePrompt)
        if 1:
            self.interactive_quit = LabeledLine(
                self.program, self, "Save changes? (yes, no, or cancel): "
            )
            self.interactive_quit.set_controller(app.cu_editor.InteractiveQuit)
        if 1:
            self.topInfo = TopInfo(self.program, self)
            self.topInfo.set_parent(self, 0)
            if not self.show_top_info:
                self.topInfo.detach()
        if 1:
            self.status_line = StatusLine(self.program, self)
            self.status_line.set_parent(self, 0)
            if not self.show_footer:
                self.status_line.detach()
        if 1:
            self.line_number_column = LineNumbers(self.program, self)
            self.line_number_column.set_parent(self, 0)
            if not self.show_line_numbers:
                self.line_number_column.detach()
        if 1:
            self.logo_corner = ViewWindow(self.program, self)
            self.logo_corner.name = "Logo"
            self.logo_corner.set_parent(self, 0)
        if 1:
            self.right_column = ViewWindow(self.program, self)
            self.right_column.name = "Right"
            self.right_column.set_parent(self, 0)
            if not self.show_right_column:
                self.right_column.detach()
        if 1:
            self.popup_window = PopupWindow(self.program, self)
        if self.show_message_line:
            self.messageLine = MessageLine(self.program, self)
            self.messageLine.set_parent(self, 0)
        self.show_tips = self.program.prefs.status.get("show_tips")
        self.status_line_count = 8 if self.show_tips else 1

    if 0:

        def split_window(self):
            """Experimental."""
            app.log.info()
            other = InputWindow(self.prg, self)
            other.set_text_buffer(self.text_buffer)
            app.log.info()
            self.prg.z_order.append(other)
            self.prg.layout()
            app.log.info()

    def layout(self):
        """Change self and sub-windows to fit within the given rectangle."""
        top, left, rows, cols = self.outer_shape
        line_numbers_cols = 7
        top_rows = self.top_rows
        bottom_rows = max(1, self.interactive_find.preferred_size(rows, cols)[0])

        # The top, left of the main window is the rows, cols of the logo corner.
        self.logo_corner.reshape(top, left, 2, line_numbers_cols)

        if self.show_top_info and rows > top_rows and cols > line_numbers_cols:
            self.topInfo.reshape(
                top, left + line_numbers_cols, top_rows, cols - line_numbers_cols
            )
            top += top_rows
            rows -= top_rows
        rows -= bottom_rows
        bottom_first_row = top + rows

        self.confirm_close.reshape(bottom_first_row, left, bottom_rows, cols)
        self.confirm_overwrite.reshape(bottom_first_row, left, bottom_rows, cols)
        self.interactive_prediction.reshape(bottom_first_row, left, bottom_rows, cols)
        self.interactive_prompt.reshape(bottom_first_row, left, bottom_rows, cols)
        self.interactive_quit.reshape(bottom_first_row, left, bottom_rows, cols)
        if self.show_message_line:
            self.messageLine.reshape(bottom_first_row, left, bottom_rows, cols)
        self.interactive_find.reshape(bottom_first_row, left, bottom_rows, cols)
        if 1:
            self.interactive_goto.reshape(bottom_first_row, left, bottom_rows, cols)
        if self.show_footer and rows > 0:
            self.status_line.reshape(
                bottom_first_row - self.status_line_count, left, self.status_line_count, cols
            )
            rows -= self.status_line_count
        if self.show_line_numbers and cols > line_numbers_cols:
            self.line_number_column.reshape(top, left, rows, line_numbers_cols)
            cols -= line_numbers_cols
            left += line_numbers_cols
        if self.show_right_column and cols > 0:
            self.right_column.reshape(top, left + cols - 1, rows, 1)
            cols -= 1
        Window.reshape(self, top, left, rows, cols)

    def draw_logo_corner(self):
        """."""
        logo = self.logo_corner
        if logo.rows <= 0 or logo.cols <= 0:
            return
        color = self.program.color.get("logo")
        for i in range(logo.rows):
            logo.add_str(i, 0, " " * logo.cols, color)
        logo.add_str(0, 1, "ci"[: self.cols], color)
        logo.render()

    def draw_right_edge(self):
        """Draw makers to indicate text extending past the right edge of the
        window."""
        max_row, max_col = self.rows, self.cols
        limit = min(max_row, self.text_buffer.parser.row_count() - self.scroll_row)
        colorPrefs = self.program.color
        for i in range(limit):
            color = colorPrefs.get("right_column")
            if (
                self.text_buffer.parser.row_width(i + self.scroll_row) - self.scroll_col
                > max_col
            ):
                color = colorPrefs.get("line_overflow")
            self.right_column.add_str(i, 0, " ", color)
        color = colorPrefs.get("outside_document")
        for i in range(limit, max_row):
            self.right_column.add_str(i, 0, " ", color)

    def focus(self):
        self.layout()
        if self.show_message_line:
            self.messageLine.bring_to_front()
        Window.focus(self)

    def next_focusable_window(self, start, reverse=False):
        # Keep the tab focus in the child branch. (The child view will call
        # this, tell the child there is nothing to tab to up here).
        return None

    def render(self):
        self.topInfo.on_change()
        self.draw_logo_corner()
        self.draw_right_edge()
        Window.render(self)

    def reshape(self, top, left, rows, cols):
        """Change self and sub-windows to fit within the given rectangle."""
        app.log.detail(top, left, rows, cols)
        Window.reshape(self, top, left, rows, cols)
        self.outer_shape = (top, left, rows, cols)
        self.layout()

    def set_text_buffer(self, text_buffer):
        if app.config.strict_debug:
            assert issubclass(text_buffer.__class__, app.text_buffer.TextBuffer), repr(
                text_buffer
            )
        app.log.info("set_text_buffer")
        if self.text_buffer is not None:
            self.saved_scroll_positions[self.text_buffer.full_path] = (
                self.scroll_row,
                self.scroll_col,
            )
        # self.normalize()
        text_buffer.line_limit_indicator = self.program.prefs.editor["line_limit_indicator"]
        text_buffer.debug_redo = self.program.prefs.startup.get("debug_redo")
        Window.set_text_buffer(self, text_buffer)
        self.controller.set_text_buffer(text_buffer)
        saved_scroll = self.saved_scroll_positions.get(self.text_buffer.full_path)
        if saved_scroll is not None:
            self.scroll_row, self.scroll_col = saved_scroll
        else:
            history_scroll = self.text_buffer.file_history.get("scroll")
            if history_scroll is not None:
                self.scroll_row, self.scroll_col = history_scroll
            else:
                self.text_buffer.scroll_to_optimal_scroll_position()

    def startup(self):
        buffer_manager = self.program.buffer_manager
        for f in self.program.prefs.startup.get("cli_files", []):
            tb = buffer_manager.load_text_buffer(f["path"])
            if tb is None:
                # app.log.info('failed to load', repr(f["path"]))
                continue
            tb.parse_document()
            if f["row"] is not None:
                if f["col"] is not None:
                    tb.select_text(f["row"], f["col"], 0, app.selectable.SELECTION_NONE)
                else:
                    tb.select_text(f["row"], 0, 0, app.selectable.SELECTION_NONE)
        if self.program.prefs.startup.get("read_stdin"):
            buffer_manager.read_stdin()
        buffer_manager.buffers.reverse()
        tb = buffer_manager.top_buffer()
        if not tb:
            tb = buffer_manager.new_text_buffer()
        self.set_text_buffer(tb)
        # Should parsing the document be a standard part of set_text_buffer? TBD.
        self.text_buffer.parse_document()
        open_to_line = self.program.prefs.startup.get("open_to_line")
        if open_to_line is not None:
            self.text_buffer.select_text(
                open_to_line - 1, 0, 0, app.selectable.SELECTION_NONE
            )

    def toggle_show_tips(self):
        self.show_tips = not self.show_tips
        self.status_line_count = 8 if self.show_tips else 1
        self.layout()
        self.program.prefs.save("status", "show_tips", self.show_tips)

    def unfocus(self):
        if self.show_message_line:
            self.messageLine.detach()
        Window.unfocus(self)

class OptionsSelectionWindow(ViewWindow):
    """Mutex window."""

    def __init__(self, program, parent):
        if app.config.strict_debug:
            assert parent is not None
        ViewWindow.__init__(self, program, parent)
        self.color = self.program.color.get("top_info")

    def reshape(self, top, left, rows, cols):
        ViewWindow.reshape(self, top, left, rows, cols)
        self.layout_horizontally(self.z_order)

    def child_selected(self, selected_child):
        app.log.info(self.z_order)
        for child in self.z_order:
            if child is not selected_child:
                child.deselect()

    def render(self):
        self.blank(self.color)
        ViewWindow.render(self)

class OptionsTrinaryStateWindow(Window):
    def __init__(self, program, parent, label, pref_category, pref_name):
        if app.config.strict_debug:
            assert isinstance(label, unicode)
            assert isinstance(pref_category, unicode)
            assert isinstance(pref_name, unicode)
        Window.__init__(self, program, parent)
        # TODO(dschuyler): Creating a text buffer is rather heavy for a toggle
        # control. This should get some optimization.
        self.set_text_buffer(app.text_buffer.TextBuffer(self.program))
        self.set_controller(app.cu_editor.ToggleController)
        self.set_parent(parent)
        self.name = label
        self.pref_category = pref_category
        self.pref_name = pref_name
        colorPrefs = self.program.color
        self.color = colorPrefs.get("keyword")
        self.focus_color = colorPrefs.get("selected")
        self.text_buffer.view.show_cursor = False

    def focus(self):
        Window.focus(self)

    def set_up(self, toggle_on, toggle_off, toggle_undefined, width=None):
        if app.config.strict_debug:
            assert isinstance(toggle_on, unicode)
            assert isinstance(toggle_off, unicode)
            assert isinstance(toggle_undefined, unicode)
            assert width is None or isinstance(width, int)
        self.toggle_on = toggle_on
        self.toggle_off = toggle_off
        self.toggle_undefined = toggle_undefined
        longest = max(len(toggle_on), len(toggle_off), len(toggle_undefined))
        self.width = width if width is not None else longest
        self.update_label()

    def mouse_click(self, pane_row, pane_col, shift, ctrl, alt):
        self.controller.toggle_value()

    def on_pref_changed(self, category, name):
        Window.on_pref_changed(self, category, name)
        if category != self.pref_category or name != self.pref_name:
            return
        self.update_label()

    def update_label(self):
        pref = self.program.prefs.category(self.pref_category)[self.pref_name]
        if pref is None:
            label = self.toggle_undefined
        else:
            label = self.toggle_on if pref else self.toggle_off
        self.label = "%*s" % (self.width, label)

    def preferred_size(self, row_limit, col_limit):
        return min(row_limit, 1), min(col_limit, abs(self.width))

    def render(self):
        Window.render(self)
        if self.rows <= 0:
            return
        self.writeLineRow = 0
        color = self.focus_color if self.has_focus else self.color
        self.write_line(self.label[: self.cols], color)

class OptionsToggle(OptionsTrinaryStateWindow):
    def __init__(self, program, parent, label, pref_category, pref_name, width=None):
        if app.config.strict_debug:
            assert isinstance(label, unicode)
            assert isinstance(pref_category, unicode)
            assert isinstance(pref_name, unicode)
        OptionsTrinaryStateWindow.__init__(
            self, program, parent, label, pref_category, pref_name
        )
        # I considered these unicode characters, but [x] looks clearer to me.
        # toggle_on = unichr(0x2612) + ' ' + control['name']
        # toggle_off = unichr(0x2610) + ' ' + control['name']
        OptionsTrinaryStateWindow.set_up(
            self, "[x]" + label, "[ ]" + label, "[-]" + label, width
        )

class RowWindow(ViewWindow):
    def __init__(self, program, host, separator):
        if app.config.strict_debug:
            assert host
        ViewWindow.__init__(self, program, host)
        self.color = self.program.color.get("keyword")
        self.separator = separator

    def preferred_size(self, row_limit, col_limit):
        return min(row_limit, 1), col_limit

    def render(self):
        self.blank(self.color)
        ViewWindow.render(self)

    def reshape(self, top, left, rows, cols):
        ViewWindow.reshape(self, top, left, rows, cols)
        # app.log.info(top, left, rows, cols, self)
        self.layout_horizontally(self.z_order, self.separator)

class OptionsRow(ViewWindow):
    class ControlElement:
        def __init__(self, element_type, name, reference, width=None, sep=" "):
            self.type = element_type
            self.name = name
            self.reference = reference
            self.width = width if width is not None else len(name)
            self.sep = sep

    def __init__(self, program, host):
        if app.config.strict_debug:
            assert host
        ViewWindow.__init__(self, program, host)
        self.host = host
        self.color = self.program.color.get("top_info")
        self.control_list = []
        self.group = None

    def add_element(self, draw, kind, name, reference, width, sep, extra_width=0):
        if app.config.strict_debug:
            assert isinstance(name, unicode)
            assert isinstance(sep, unicode)
            assert width is None or isinstance(width, int)
            assert isinstance(extra_width, int)
            if reference is not None:
                assert isinstance(reference, dict)
                assert name in reference
        if self.group is not None:
            self.group.append(len(self.control_list))
        element = {
            "dict": reference,
            "draw": draw,
            "name": name,
            "sep": sep,
            "type": kind,
            "width": width if width is not None else len(name) + extra_width,
        }
        self.control_list.append(element)
        return element

    def add_label(self, name, width=None, sep=" "):
        def draw(control):
            return control["name"]

        return self.add_element(draw, "label", name, None, width, sep)

    def add_sort_header(self, name, reference, width=None, sep=" |"):
        def draw(control):
            decoration = "v" if control["dict"][control["name"]] else "^"
            if control["dict"][control["name"]] is None:
                decoration = "-"
            if control["width"] < 0:
                return f"{control['name']} {decoration}"
            return f"{decoration} {control['name']}"

        self.add_element(draw, "sort", name, reference, width, sep, len(" v"))

    def add_selection(self, name, reference, width=None, sep="  "):
        if app.config.strict_debug:
            assert isinstance(name, unicode)
        if 1:
            toggle_on = "(*)" + name
            toggle_off = "( )" + name

        def draw(control):
            return toggle_on if control["dict"][control["name"]] else toggle_off

        width = max(width, min(len(toggle_on), len(toggle_off)))
        self.add_element(draw, "selection", name, reference, width, sep, len("(*)"))

    def remove_this_add_toggle(self, name, reference, width=None, sep="  "):
        if app.config.strict_debug:
            assert isinstance(name, unicode)
        if 1:
            toggle_on = "[x]" + name
            toggle_off = "[ ]" + name
        if 0:
            toggle_on = unichr(0x2612) + " " + control["name"]
            toggle_off = unichr(0x2610) + " " + control["name"]
        if 0:
            toggle_on = "[+" + control["name"] + "]"
            toggle_off = "[-" + control["name"] + "]"

        def draw(control):
            return toggle_on if control["dict"][control["name"]] else toggle_off

        width = max(width, min(len(toggle_on), len(toggle_off)))
        self.add_element(draw, "toggle", name, reference, width, sep, len("[-]"))

    def begin_group(self):
        """Like a radio group, or column sort headers."""
        self.group = []

    def end_group(self):
        """Like a radio group, or column sort headers."""
        pass

    def mouse_click(self, pane_row, pane_col, shift, ctrl, alt):
        # row = self.scroll_row + pane_row
        col = self.scroll_col + pane_col
        offset = 0
        for index, control in enumerate(self.control_list):
            width = abs(control["width"])
            if offset <= col < offset + width:
                if control["type"] == "selection":
                    name = control["name"]
                    for element in self.group:
                        element_name = self.control_list[element]["name"]
                        self.control_list[element]["dict"][element_name] = False
                    control["dict"][name] = True
                    self.host.controller.option_changed(name, control["dict"][name])
                    break
                if control["type"] == "sort":
                    name = control["name"]
                    new_value = not control["dict"][name]
                    if index in self.group:
                        for element in self.group:
                            element_name = self.control_list[element]["name"]
                            self.control_list[element]["dict"][element_name] = None
                    control["dict"][name] = new_value
                    self.host.controller.option_changed(name, control["dict"][name])
                    break
                if control["type"] == "toggle":
                    name = control["name"]
                    control["dict"][name] = not control["dict"][name]
                    self.host.controller.option_changed(name, control["dict"][name])
                    break
            offset += width + len(control["sep"])

    def preferred_size(self, row_limit, col_limit):
        return min(row_limit, 1), col_limit

    def render(self):
        if self.rows <= 0:
            return
        line = ""
        for control in self.control_list:
            label = control["draw"](control)
            line += "%*s%s" % (control["width"], label, control["sep"])
            if len(line) >= self.cols:
                break
        self.writeLineRow = 0
        self.write_line(line[: self.cols], self.color)

class PopupWindow(Window):
    def __init__(self, program, host):
        if app.config.strict_debug:
            assert host
        Window.__init__(self, program, host)
        self.host = host
        self.controller = app.cu_editor.PopupController(self)
        self.set_text_buffer(app.text_buffer.TextBuffer(self.program))
        self.longest_line_length = 0
        self.__message = []
        self.show_options = True
        # This will be displayed and should contain the keys that respond to
        # user input. This should be updated if you change the controller's
        # command set.
        self.options = []

    def render(self):
        """Display a box of text in the center of the window."""
        max_rows, max_cols = self.host.rows, self.host.cols
        cols = min(self.longest_line_length + 6, max_cols)
        rows = min(len(self.__message) + 4, max_rows)
        self.resize_to(rows, cols)
        self.move_to(max_rows // 2 - rows // 2, max_cols // 2 - cols // 2)
        color = self.program.color.get("popup_window")
        for row in range(rows):
            if row == rows - 2 and self.show_options:
                message = "/".join(self.options)
            elif row == 0 or row >= rows - 3:
                self.add_str(row, 0, " " * cols, color)
                continue
            else:
                message = self.__message[row - 1]
            line_length = len(message)
            spacing1 = (cols - line_length) // 2
            spacing2 = cols - line_length - spacing1
            self.add_str(row, 0, " " * spacing1 + message + " " * spacing2, color)

    def set_message(self, message):
        """Sets the Popup window's message to the given message.

        message (str): A string that you want to display.

        Returns:
          None.
        """
        self.__message = message.split("\n")
        self.longest_line_length = max([len(line) for line in self.__message])

    def set_options_to_display(self, options):
        """
        This function is used to change the options that are displayed in the
        popup window. They will be separated by a '/' character when displayed.

        Args:
          options (list): A list of possible keys which the user can press and
                          should be responded to by the controller.
        """
        self.options = options

    def set_text_buffer(self, text_buffer):
        Window.set_text_buffer(self, text_buffer)
        self.controller.set_text_buffer(text_buffer)

    def unfocus(self):
        self.detach()
        Window.unfocus(self)

class PaletteWindow(Window):
    """A window with example foreground and background text colors."""

    def __init__(self, prg, host):
        Window.__init__(self, prg, host)
        self.prg = prg
        self.resize_to(16, 16 * 5)
        self.move_to(8, 8)
        self.controller = app.cu_editor.PaletteDialogController(self)
        self.set_text_buffer(app.text_buffer.TextBuffer(self.program))

    def render(self):
        width = 16
        rows = 16
        colorPrefs = self.program.color
        for i in range(width):
            for k in range(rows):
                self.add_str(
                    k, i * 5, f" {i + k * width:3d} ", colorPrefs.get(i + k * width)
                )

    def set_text_buffer(self, text_buffer):
        Window.set_text_buffer(self, text_buffer)
        self.controller.set_text_buffer(text_buffer)

    def unfocus(self):
        self.detach()
        Window.unfocus(self)

class SortableHeaderWindow(OptionsTrinaryStateWindow):
    def __init__(self, program, parent, label, pref_category, pref_name, width=None):
        if app.config.strict_debug:
            assert issubclass(program.__class__, app.ci_program.CiProgram), program
            assert isinstance(label, unicode)
            assert isinstance(pref_category, unicode)
            assert isinstance(pref_name, unicode)
        OptionsTrinaryStateWindow.__init__(
            self, program, parent, label, pref_category, pref_name
        )
        self.color = self.program.color.get("top_info")

        def draw(label, decoration, width):
            if width < 0:
                x = f"{label} {decoration}"
            else:
                x = f"{decoration} {label}"
            return "%*s" % (width, x)

        OptionsTrinaryStateWindow.set_up(
            self,
            draw(label, "v", width),
            draw(label, "^", width),
            draw(label, "-", width),
        )

    def deselect(self):
        self.controller.clear_value()

    def mouse_click(self, pane_row, pane_col, shift, ctrl, alt):
        self.parent.child_selected(self)
        self.controller.toggle_value()
