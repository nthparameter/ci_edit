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
"""Interactive prompt to run advanced commands and sub-processes."""

try:
    unicode
except NameError:
    unicode = str
    unichr = chr

import os
import re
import subprocess

import app.controller
import app.formatter

def function_test_eq(a, b):
    assert a == b, f"{a!r} != {b!r}"

if 1:
    # Break up a command line, separate by |.
    RE_PIPE_CHAIN = re.compile(
        # r'''\|\|?|&&|((?:"(?:\\"|[^"])*"|'(?:\\'|[^'])*'|[^\s|&]+)+)''')
        r"""((?:"(?:\\"|[^"])*"|'(?:\\'|[^'])*'|\|\||[^|]+)+)"""
    )
    function_test_eq(
        RE_PIPE_CHAIN.findall(""" date "a b" 'c d ' | sort """),
        [""" date "a b" 'c d ' """, " sort "],
    )
    function_test_eq(RE_PIPE_CHAIN.findall("date"), ["date"])
    function_test_eq(RE_PIPE_CHAIN.findall("d-a.te"), ["d-a.te"])
    function_test_eq(RE_PIPE_CHAIN.findall("date | wc"), ["date ", " wc"])
    function_test_eq(RE_PIPE_CHAIN.findall("date|wc"), ["date", "wc"])
    function_test_eq(RE_PIPE_CHAIN.findall("date && sort"), ["date && sort"])
    function_test_eq(RE_PIPE_CHAIN.findall("date || sort"), ["date || sort"])
    function_test_eq(
        RE_PIPE_CHAIN.findall("""date "a b" 'c d ' || sort"""),
        ["""date "a b" 'c d ' || sort"""],
    )

# Break up a command line, separate by &&.
RE_LOGIC_CHAIN = re.compile(
    r"""\s*(\|\|?|&&|"(?:\\"|[^"])*"|'(?:\\'|[^'])*'|[^\s|&]+)"""
)
function_test_eq(RE_LOGIC_CHAIN.findall("date"), ["date"])
function_test_eq(RE_LOGIC_CHAIN.findall("d-a.te"), ["d-a.te"])
function_test_eq(RE_LOGIC_CHAIN.findall("date | wc"), ["date", "|", "wc"])
function_test_eq(RE_LOGIC_CHAIN.findall("date|wc"), ["date", "|", "wc"])
function_test_eq(RE_LOGIC_CHAIN.findall("date && sort"), ["date", "&&", "sort"])
function_test_eq(RE_LOGIC_CHAIN.findall("date || sort"), ["date", "||", "sort"])
function_test_eq(
    RE_LOGIC_CHAIN.findall(""" date "a\\" b" 'c d ' || sort """),
    ["date", '"a\\" b"', "'c d '", "||", "sort"],
)

# Break up a command line, separate by \\s.
RE_ARG_CHAIN = re.compile(r"""\s*("(?:\\"|[^"])*"|'(?:\\'|[^'])*'|[^\s]+)""")
function_test_eq(RE_ARG_CHAIN.findall("date"), ["date"])
function_test_eq(RE_ARG_CHAIN.findall("d-a.te"), ["d-a.te"])
function_test_eq(
    RE_ARG_CHAIN.findall(""" date "a b" 'c d ' "a\\" b" 'c\\' d ' """),
    ["date", '"a b"', "'c d '", '"a\\" b"', "'c\\' d '"],
)
function_test_eq(RE_ARG_CHAIN.findall("""bm +"""), ["bm", "+"])

# Break up a command line, separate by \w (non-word chars will be separated).
RE_SPLIT_CMD_LINE = re.compile(r"""\s*("(?:\\"|[^"])*"|'(?:\\'|[^'])*'|\w+|[^\s]+)\s*""")
function_test_eq(RE_SPLIT_CMD_LINE.findall("""bm ab"""), ["bm", "ab"])
function_test_eq(RE_SPLIT_CMD_LINE.findall("""bm+"""), ["bm", "+"])
function_test_eq(RE_SPLIT_CMD_LINE.findall('''bm "one two"'''), ["bm", '"one two"'])
function_test_eq(RE_SPLIT_CMD_LINE.findall('''bm "o\\"ne two"'''), ["bm", '"o\\"ne two"'])

# Unquote text.
RE_UNQUOTE = re.compile(r"""(["'])([^\1]*)\1""")
function_test_eq(RE_UNQUOTE.sub("\\2", "date"), "date")
function_test_eq(RE_UNQUOTE.sub("\\2", '"date"'), "date")
function_test_eq(RE_UNQUOTE.sub("\\2", "'date'"), "date")
function_test_eq(RE_UNQUOTE.sub("\\2", "'da\\'te'"), "da\\'te")
function_test_eq(RE_UNQUOTE.sub("\\2", '"da\\"te"'), 'da\\"te')

class InteractivePrompt(app.controller.Controller):
    """Extended commands prompt."""

    def __init__(self, view):
        app.controller.Controller.__init__(self, view, "prompt")

    def set_text_buffer(self, textBuffer):
        app.controller.Controller.set_text_buffer(self, textBuffer)
        self.textBuffer = textBuffer
        self.commands = {
            "bm": self.bookmark_command,
            "build": self.build_command,
            "cua": self.change_to_cua_mode,
            "emacs": self.change_to_emacs_mode,
            "make": self.make_command,
            "open": self.open_command,
            # 'split': self.split_command,  # Experimental wip.
            "vim": self.change_to_vim_normal_mode,
        }
        self.filters = {
            "format": self.format_command,
            "lower": self.lower_selected_lines,
            "numEnum": self.assign_index_to_selected_lines,
            "s": self.substitute_text,
            "sort": self.sort_selected_lines,
            "sub": self.substitute_text,
            "upper": self.upper_selected_lines,
            "wrap": self.wrap_selected_lines,
        }
        self.sub_execute = {
            "!": self.shell_execute,
            "|": self.pipe_execute,
        }

    def bookmark_command(self, cmdLine, view):
        args = RE_SPLIT_CMD_LINE.findall(cmdLine)
        if len(args) > 1 and args[1][0] == "-":
            if self.view.host.textBuffer.bookmark_remove():
                return {}, "Removed bookmark"
            else:
                return {}, "No bookmarks to remove"
        else:
            self.view.host.textBuffer.bookmark_add()
            return {}, "Added bookmark"

    def build_command(self, cmdLine, view):
        return {}, "building things"

    def change_to_cua_mode(self, cmdLine, view):
        return {}, "CUA mode"

    def change_to_emacs_mode(self, cmdLine, view):
        return {}, "Emacs mode"

    def change_to_vim_normal_mode(self, cmdLine, view):
        return {}, "Vim normal mode"

    def focus(self):
        app.log.info("InteractivePrompt.focus")
        self.textBuffer.selection_all()

    def format_command(self, cmdLine, lines):
        formatters = {
            # ".js": app.format_javascript.format
            # ".html": app.format_html.format,
            ".py": app.formatter.format_python
        }

        fileName, ext = os.path.splitext(self.view.host.textBuffer.full_path)

        app.log.info(fileName, ext)
        formatter = formatters.get(ext)

        if not formatter:
            return lines, f"No formatter for extension {ext}"

        try:
            formattedText = formatter(self.view.host.textBuffer.parser.data)
        except RuntimeError as err:
            return lines, str(err)

        lines = formattedText.split("\n")
        return lines, f"Changed {len(lines)} lines"

    def make_command(self, cmdLine, view):
        return {}, "making stuff"

    def open_command(self, cmdLine, view):
        """
        Opens the file under cursor.
        """
        args = RE_ARG_CHAIN.findall(cmdLine)
        app.log.info(args)
        if len(args) == 1:
            # If no args are provided, look for a path at the cursor position.
            view.textBuffer.open_file_at_cursor()
            return {}, view.textBuffer.message[0]
        # Try the raw path.
        path = args[1]
        if os.access(path, os.R_OK):
            return self.open_file(path, view)
        # Look in the same directory as the current file.
        path = os.path.join(os.path.dirname(view.textBuffer.full_path), args[1])
        if os.access(path, os.R_OK):
            return self.open_file(path, view)
        return {}, "Unable to open " + args[1]

    def open_file(self, path, view):
        textBuffer = view.program.buffer_manager.load_text_buffer(path)
        inputWindow = self.current_input_window()
        inputWindow.set_text_buffer(textBuffer)
        self.change_to(inputWindow)
        inputWindow.set_message(f"Opened file {path}")

    def split_command(self, cmdLine, view):
        view.split_window()
        return {}, "Split window"

    def execute(self):
        try:
            cmdLine = self.textBuffer.parser.data
            if not len(cmdLine):
                self.change_to_host_window()
                return
            tb = self.view.host.textBuffer
            lines = list(tb.get_selected_text())
            if cmdLine[0] in self.sub_execute:
                data = "\n".join(lines).encode("utf-8")
                output, message = self.sub_execute.get(cmdLine[0])(cmdLine[1:], data)
                if app.config.strict_debug:
                    assert isinstance(output, bytes)
                    assert isinstance(message, unicode)
                tb.edit_paste_lines(tuple(output.decode("utf-8").split("\n")))
                tb.set_message(message)
            else:
                cmd = re.split("\\W", cmdLine)[0]
                dataFilter = self.filters.get(cmd)
                if dataFilter:
                    if not len(lines):
                        tb.set_message(f"The {cmd} filter needs a selection.")
                    else:
                        lines, message = dataFilter(cmdLine, lines)
                        tb.set_message(message)
                        if not len(lines):
                            lines.append("")
                        tb.edit_paste_lines(tuple(lines))
                else:
                    command = self.commands.get(cmd, self.unknown_command)
                    message = command(cmdLine, self.view.host)[1]
                    tb.set_message(message)
        except Exception as e:
            app.log.exception(e)
            tb.set_message("Execution threw an error.")
        self.change_to_host_window()

    def shell_execute(self, commands, cmdInput):
        """
        cmdInput is in bytes (not unicode).
        return tuple: output as bytes (not unicode), message as unicode.
        """
        if app.config.strict_debug:
            assert isinstance(commands, unicode), type(commands)
            assert isinstance(cmdInput, bytes), type(cmdInput)
        try:
            process = subprocess.Popen(
                commands,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=True,
            )
            return process.communicate(cmdInput)[0], ""
        except Exception as e:
            return "", "Error running shell command\n" + e

    def pipe_execute(self, commands, cmdInput):
        """
        cmdInput is in bytes (not unicode).
        return tuple: output as bytes (not unicode), message as unicode.
        """
        if app.config.strict_debug:
            assert isinstance(commands, unicode), type(commands)
            assert isinstance(cmdInput, bytes), type(cmdInput)
        chain = RE_PIPE_CHAIN.findall(commands)
        try:
            process = subprocess.Popen(
                RE_ARG_CHAIN.findall(chain[-1]),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            if len(chain) == 1:
                return process.communicate(cmdInput)[0], ""
            else:
                chain.reverse()
                prior = process
                for i in chain[1:]:
                    prior = subprocess.Popen(
                        RE_ARG_CHAIN.findall(i),
                        stdin=subprocess.PIPE,
                        stdout=prior.stdin,
                        stderr=subprocess.STDOUT,
                    )
                prior.communicate(cmdInput)
                return process.communicate()[0], ""
        except Exception as e:
            app.log.exception(e)
            return b"", "Error running shell command\n" + unicode(e)

    def info(self):
        app.log.info("InteractivePrompt command set")

    def lower_selected_lines(self, cmdLine, lines):
        lines = [line.lower() for line in lines]
        return lines, f"Changed {len(lines)} lines"

    def assign_index_to_selected_lines(self, cmdLine, lines):
        output = []
        for i, line in enumerate(lines):
            output.append("%s = %d" % (line, i))
        return output, f"Changed {len(output)} lines"

    def sort_selected_lines(self, cmdLine, lines):
        lines.sort()
        return lines, f"Changed {len(lines)} lines"

    def substitute_text(self, cmdLine, lines):
        if len(cmdLine) < 2:
            return (
                lines,
                f"""tip: {cmdLine}/foo/bar/ to replace 'foo' with 'bar'.""",
            )
        if not lines:
            return lines, "No text was selected."
        sre = re.match("\w+(\W)", cmdLine)
        if not sre:
            return (
                lines,
                f"""Separator punctuation missing, example: {cmdLine}/foo/bar/""",
            )
        separator = sre.groups()[0]
        try:
            _, find, replace, flags = cmdLine.split(separator, 3)
        except ValueError:
            return (
                lines,
                """Separator punctuation missing, there should be"""
                """ three '%s'.""" % (separator,),
            )
        data = self.view.host.textBuffer.parser.data
        output = self.view.host.textBuffer.find_replace_text(find, replace, flags, data)
        lines = output.split("\n")
        return lines, f"Changed {len(lines)} lines"

    def upper_selected_lines(self, cmdLine, lines):
        lines = [line.upper() for line in lines]
        return lines, f"Changed {len(lines)} lines"

    def unknown_command(self, cmdLine, view):
        self.view.host.textBuffer.set_message("Unknown command")
        return {}, f"Unknown command {cmdLine}"

    def wrap_selected_lines(self, cmdLine, lines):
        tokens = cmdLine.split()
        app.log.info("tokens", tokens)
        width = 80 if len(tokens) == 1 else int(tokens[1])
        indent = len(lines[0]) - len(lines[0].lstrip())
        width -= indent
        lines = app.curses_util.wrap_lines(lines, " " * indent, width)
        return lines, f"Changed {len(lines)} lines"
