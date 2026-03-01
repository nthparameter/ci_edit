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

import app.config

ENCODE = {
    "\\": "\\\\",
    "\a": "\\a",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\v": "\\v",
    "\x7f": "\\x7f",
}

DECODE = {
    "\\": "\\",
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
}

def path_encode(path):
    if app.config.strict_debug:
        assert isinstance(path, unicode), repr(path)
    out = ""
    for i in range(len(path)):
        c = path[i]
        ord_c = ord(c)
        t = ENCODE.get(c)
        if t is not None:
            c = t
        elif ord_c < 32:
            c = f"\\x{ord_c:02x}"
        out += c
    return out

def path_decode(path):
    if app.config.strict_debug:
        assert isinstance(path, unicode)
    out = ""
    limit = len(path)
    i = 0
    while i < limit:
        c = path[i]
        i += 1
        if c == "\\":
            if i >= len(path):
                out += "\\"
                break
            c = path[i]
            i += 1
            if c == "x":
                c = unichr(path[i - 1 : i + 3])
            elif c == "" or c == "o":
                c = unichr(path[i - 1 : i + 5])
            elif c == "U":
                c = unichr(path[i - 1 : i + 9])
            else:
                c = DECODE.get(c, "\\")
        out += c
    return out
