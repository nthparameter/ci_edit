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

import curses
import json
import os
import re
import sys

import app.default_prefs
import app.log
import app.regex

class Prefs:
    def __init__(self):
        self.prefs_directory = "~/.ci_edit/prefs/"
        prefs = app.default_prefs.prefs
        self.color8 = app.default_prefs.color8
        self.color16 = app.default_prefs.color16
        self.color256 = app.default_prefs.color256
        self.color = self.color256
        self.dictionaries = prefs.get("dictionaries", [])
        self.editor = prefs.get("editor", {})
        self.dev_test = prefs.get("dev_test", {})
        self.palette = prefs.get("palette", {})
        self.startup = {}
        self.status = prefs.get("status", {})
        self.user_data = prefs.get("user_data", {})
        self.__set_up_grammars(prefs.get("grammar", {}))
        self.__set_up_file_types(prefs.get("file_type", {}))
        self.init()

    def load_prefs(self, file_name, category):
        # Check the user home directory for preferences.
        prefs_path = os.path.expanduser(
            os.path.expandvars(
                os.path.join(self.prefs_directory, f"{file_name}.json")
            )
        )
        if os.path.isfile(prefs_path) and os.access(prefs_path, os.R_OK):
            with open(prefs_path, "r") as f:
                try:
                    additional_prefs = json.loads(f.read())
                    app.log.startup(additional_prefs)
                    category.update(additional_prefs)
                    app.log.startup("Updated editor prefs from", prefs_path)
                    app.log.startup("as", category)
                except Exception as e:
                    app.log.startup("failed to parse", prefs_path)
                    app.log.startup("error", e)
        return category

    def init(self):
        self.editor = self.load_prefs("editor", self.editor)
        self.status = self.load_prefs("status", self.status)

        self.color_scheme_name = self.editor["color_scheme"]
        if self.color_scheme_name == "custom":
            # Check the user home directory for a color scheme preference. If
            # found load it to replace the default color scheme.
            self.color = self.load_prefs("color_scheme", self.color)

        default_color = self.color["default"]
        default_keywords_color = self.color["keyword"]
        default_specials_color = self.color["special"]
        for k, v in self.grammars.items():
            # Colors.
            v["color_index"] = self.color.get(k, default_color)
            if 0:
                v["keywords_color"] = curses.color_pair(
                    self.color.get(k + "_keyword_color", default_keywords_color)
                )
                v["specials_color"] = curses.color_pair(
                    self.color.get(k + "_special_color", default_specials_color)
                )
        app.log.info("prefs init")

    def category(self, name):
        return {
            "color": self.color,
            "editor": self.editor,
            "startup": self.startup,
        }[name]

    def get_file_type(self, file_path):
        if file_path is None:
            return self.grammars.get("text")
        name = os.path.split(file_path)[1]
        file_type = self.name_to_type.get(name)
        if file_type is None:
            file_extension = os.path.splitext(name)[1]
            file_type = self.extensions.get(file_extension, "text")
        return file_type

    def tabs_to_spaces(self, file_type):
        prefs = app.default_prefs.prefs.get("file_type", {})
        if file_type is None or prefs is None:
            return False
        file_prefs = prefs.get(file_type)
        return file_prefs and file_prefs.get("tab_to_spaces")

    def get_grammar(self, file_type):
        return self.grammars.get(file_type)

    def save(self, category, label, value):
        app.log.info(category, label, value)
        pref_category = self.category(category)
        pref_category[label] = value
        prefs_path = os.path.expanduser(
            os.path.expandvars(
                os.path.join(self.prefs_directory, f"{category}.json")
            )
        )
        with open(prefs_path, "w", encoding="utf-8") as f:
            try:
                f.write(json.dumps(prefs[category]))
            except Exception as e:
                app.log.error("error writing prefs")
                app.log.exception(e)

    def _raise_grammar_not_found(self):
        app.log.startup("Available grammars:")
        for k, v in self.grammars.items():
            app.log.startup("  ", k, ":", len(v))
        raise Exception('missing grammar for "' + grammar_name + '" in prefs.py')

    def __set_up_grammars(self, default_grammars):
        self.grammars = {}
        # Arrange all the grammars by name.
        for k, v in default_grammars.items():
            v["name"] = k
            self.grammars[k] = v

        # Compile regexes for each grammar.
        for k, v in default_grammars.items():
            if 0:
                # keywords re.
                v["keywords_re"] = re.compile(
                    app.regex.join_re_word_list(
                        v.get("keywords", []) + v.get("types", [])
                    )
                )
                v["errors_re"] = re.compile(app.regex.join_re_list(v.get("errors", [])))
                v["specials_re"] = re.compile(
                    app.regex.join_re_list(v.get("special", []))
                )
            # contains and end re.
            match_grammars = []
            markers = []
            # Index [0]
            if v.get("escaped"):
                markers.append(v["escaped"])
                match_grammars.append(v)
            else:
                # Add a non-matchable placeholder.
                markers.append(app.regex.RE_NON_MATCHING)
                match_grammars.append(None)
            # Index [1]
            if v.get("end"):
                markers.append(v["end"])
                match_grammars.append(v)
            else:
                # Add a non-matchable placeholder.
                markers.append(app.regex.RE_NON_MATCHING)
                match_grammars.append(None)
            # |Contains| markers start at index 2.
            for grammar_name in v.get("contains", []):
                g = self.grammars.get(grammar_name, None)
                if g is None:
                    self._raise_grammar_not_found()
                markers.append(g.get("begin", g.get("matches", "")))
                match_grammars.append(g)
            # |Next| markers start after |contains|.
            for grammar_name in v.get("next", []):
                g = self.grammars.get(grammar_name, None)
                if g is None:
                    self._raise_grammar_not_found()
                markers.append(g["begin"])
                match_grammars.append(g)
            # |Errors| markers start after |next| markers.
            markers += v.get("errors", [])
            # |Keywords| markers start after |errors| markers.
            for keyword in v.get("keywords", []):
                markers.append(r"\b" + keyword + r"\b")
            # |Types| markers start after |keywords| markers.
            for types in v.get("types", []):
                markers.append(r"\b" + types + r"\b")
            # |Special| markers start after |types| markers.
            markers += v.get("special", [])
            # Variable width characters are at index [-3] in markers.
            markers.append(r"\t+")
            # Potentially double wide characters are at index [-2] in markers.
            markers.append("[\U00001100-\U000fffff]+")
            # Carriage return characters are at index [-1] in markers.
            markers.append(r"\n")
            # app.log.startup('markers', v['name'], markers)
            v["match_re"] = re.compile(app.regex.join_re_list(markers))
            v["markers"] = markers
            v["match_grammars"] = match_grammars
            contains_grammar_index_limit = 2 + len(v.get("contains", []))
            next_grammar_index_limit = contains_grammar_index_limit + len(v.get("next", []))
            error_index_limit = next_grammar_index_limit + len(v.get("errors", []))
            keyword_index_limit = error_index_limit + len(v.get("keywords", []))
            type_index_limit = keyword_index_limit + len(v.get("types", []))
            special_index_limit = type_index_limit + len(v.get("special", []))
            v["index_limits"] = (
                contains_grammar_index_limit,
                next_grammar_index_limit,
                error_index_limit,
                keyword_index_limit,
                type_index_limit,
                special_index_limit,
            )

        # Reset the re.cache for user regexes.
        re.purge()

    def __set_up_file_types(self, default_file_types):
        self.name_to_type = {}
        self.extensions = {}
        file_types = {}
        for k, v in default_file_types.items():
            for name in v.get("name", []):
                self.name_to_type[name] = v.get("grammar")
            for ext in v["ext"]:
                self.extensions[ext] = v.get("grammar")
            file_types[k] = v
        if 0:
            app.log.info("extensions")
            for k, v in extensions.items():
                app.log.info("  ", k, ":", v)
            app.log.info("file_types")
            for k, v in file_types.items():
                app.log.info("  ", k, ":", v)
