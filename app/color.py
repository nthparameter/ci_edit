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

import curses

class Colors:
    def __init__(self, colorPrefs):
        self.__colorPrefs = colorPrefs
        self.colors = 256
        self.__cache = {}

    def get(self, color_type, delta=0):
        if type(color_type) == type(0):
            color_index = color_type
        else:
            color_index = self.__colorPrefs[color_type]
        color_index = min(self.colors - 1, color_index + delta)
        color = self.__cache.get(color_index) or curses.color_pair(color_index)
        self.__cache[color_index] = color
        if color_type in ("error", "misspelling"):
            color |= curses.A_BOLD | curses.A_REVERSE
        return color
