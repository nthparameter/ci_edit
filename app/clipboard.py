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

import third_party.pyperclip as clipboard

import app.config

class Clipboard:
    def __init__(self):
        self._clipList = []
        self.set_os_handlers(clipboard.copy, clipboard.paste)

    def copy(self, text):
        """Add text onto clip_list. Empty |text| is not stored."""
        if app.config.strict_debug:
            assert isinstance(text, unicode), type(text)
        if text and len(text):
            self._clipList.append(text)
            if self._copy:
                self._copy(text)

    def paste(self, clip_index=None):
        """Fetch top of clip_list; or clip at index |clip_index|. The |clip_index|
        will wrap around if it's larger than the clip_list length."""
        if app.config.strict_debug:
            assert clip_index is None or isinstance(clip_index, int)
        if clip_index is None:
            os_clip = self._paste and self._paste()
            if os_clip:
                return os_clip
            # Get the top of the clip_list instead.
            clip_index = -1
        if len(self._clipList):
            return self._clipList[clip_index % len(self._clipList)]
        return None

    def set_os_handlers(self, copy, paste):
        self._copy = copy
        self._paste = paste
