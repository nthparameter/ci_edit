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

import app.config

def path_row_column(path, project_dir):
    """Guess whether unrecognized file path refers to another file or has line
    and column information.

    Try to convert an unrecognized path to an exiting file.
    E.g.
    In `git diff` an 'a/' or 'b/' may be prepended to the path. Or in a compiler
    error ':<line number>' may be appended. If the file doesn't exist as-is, try
    removing those decorations, and if that exists use that path instead.

    Returns: (full_path, open_to_row, open_to_col)
    """
    if app.config.strict_debug:
        assert isinstance(path, unicode)
        assert project_dir is None or isinstance(project_dir, unicode)
    open_to_row = None
    open_to_column = None
    if os.path.isfile(path):  # or os.path.isdir(os.path.dirname(path)):
        return path, open_to_row, open_to_column
    pieces = path.split(":")
    if pieces[-1] == "":
        if len(pieces) == 3:
            try:
                open_to_row = int(pieces[1]) - 1
            except ValueError:
                pass
        elif len(pieces) == 4:
            try:
                open_to_row = int(pieces[1]) - 1
                open_to_column = int(pieces[2]) - 1
            except ValueError:
                pass
    else:
        if len(pieces) == 2:
            try:
                open_to_row = int(pieces[1]) - 1
            except ValueError:
                pass
        elif len(pieces) == 3:
            try:
                open_to_row = int(pieces[1]) - 1
                open_to_column = int(pieces[2]) - 1
            except ValueError:
                pass
    if open_to_row is not None:
        path = pieces[0]
    if len(path) > 2:  #  and not os.path.isdir(path[:2]):
        if project_dir is not None and path.startswith("//"):
            path = project_dir + path[1:]
        elif path[1] == "/":
            if os.path.isfile(path[2:]):
                path = path[2:]
    return path, open_to_row, open_to_column

def expand_full_path(path):
    return os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
