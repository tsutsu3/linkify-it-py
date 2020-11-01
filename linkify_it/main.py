import copy
import re
import sys
import types

from .ucre import build_re

if sys.version_info[1] == 6:
    RE_TYPE = re._pattern_type
elif sys.version_info[1] > 6:
    RE_TYPE = re.Pattern


# =============================================================================
# Helpers
# =============================================================================
def escape_re(string):
    ESCAPE_RE = re.compile(r"[.?*+^$[\]\\(){}|-]")
    return ESCAPE_RE.sub("\\$&", string)


def indexOf(text, search_value):
    try:
        result = text.index(search_value)
    except ValueError:
        result = -1

    return result


class Match:
    """Match result.

    Attributes:
        schema (str): Prefix (protocol) for matched string.
        index (int): First position of matched string.
        last_index (int): Next position after matched string.
        raw (str): Matched string.
        text (str): Notmalized text of matched string.
        url (str): Normalized url of matched string.
    """

    def __repr__(self):
        return "{}.{}({!r})".format(
            self.__class__.__module__, self.__class__.__name__, self.__dict__
        )

    def __init__(self, linkifyit, shift):
        start = linkifyit._index
        end = linkifyit._last_index
        text = linkifyit._text_cache[start:end]

        self.schema = linkifyit._schema.lower()
        self.index = start + shift
        self.last_index = end + shift
        self.raw = text
        self.text = text
        self.url = text


# =============================================================================
class SchemaError(Exception):
    def __init__(self, name, val):
        message = "(LinkifyIt) Invalid schema '{}': '{}'".format(name, val)
        super().__init__(message)


# =============================================================================


class LinkifyIt:
    """Creates new linkifier instance with optional additional schemas.

    By default understands:

    - ``http(s)://...`` , ``ftp://...``, ``mailto:...`` & ``//...`` links
    - "fuzzy" links and emails (example.com, foo@bar.com).

    ``schemas`` is an object, where each key/value describes protocol/rule:

    - **key** - link prefix (usually, protocol name with ``:`` at the end, ``skype:``
      for example). `linkify-it` makes shure that prefix is not preceeded with
      alphanumeric char and symbols. Only whitespaces and punctuation allowed.
    - **value** - rule to check tail after link prefix
      - *String* - just alias to existing rule
      - *Object*
        - *validate* - validator function (should return matched length on
          success), or ``RegExp``.
        - *normalize* - optional function to normalize text & url of matched
          result (for example, for @twitter mentions).

    ``options``:

    - **fuzzyLink** - recognige URL-s without ``http(s):`` prefix. Default ``true``.
    - **fuzzyIP** - allow IPs in fuzzy links above. Can conflict with some texts
      like version numbers. Default ``false``.
    - **fuzzyEmail** - recognize emails without ``mailto:`` prefix.

    Attributes:
        schemas (dict): Optional. Additional schemas to validate (prefix/validator)
        options (dict): { fuzzyLink|fuzzyEmail|fuzzyIP: true|false }
    """

    # def build_default_schems(self, text, pos):
    #     self.default_schemas["http:"] = self._validate_http(text, pos)
    #     self.default_schemas["//"] = self._validate_double_slash(text, pos)
    #     self.default_schemas["mailto:"] = self._validate_mailto(text, pos)

    def _validate_http(self, text, pos):
        tail = text[pos:]
        if not self.re.get("http"):
            # compile lazily, because "host"-containing variables can change on
            # tlds update.
            self.re["http"] = re.compile(
                "^\\/\\/"
                + self.re["src_auth"]
                + self.re["src_host_port_strict"]
                + self.re["src_path"],
                flags=re.IGNORECASE,
            )

        founds = self.re["http"].search(tail)
        if founds:
            return len(founds.group())

        return 0

    def _validate_double_slash(self, text, pos):
        tail = text[pos:]

        if not self.re.get("not_http"):
            # compile lazily, because "host"-containing variables can change on
            # tlds update.
            self.re["not_http"] = re.compile(
                "^" + self.re["src_auth"] +
                # Don't allow single-level domains, because of false positives
                # like '//test' with code comments
                "(?:localhost|(?:(?:"
                + self.re["src_domain"]
                + ")\\.)+"
                + self.re["src_domain_root"]
                + ")"
                + self.re["src_port"]
                + self.re["src_host_terminator"]
                + self.re["src_path"],
                flags=re.IGNORECASE,
            )

        founds = self.re["not_http"].search(tail)
        if founds:
            if pos >= 3 and text[pos - 3] == ":":
                return 0

            if pos >= 3 and text[pos - 3] == "/":
                return 0

            return len(founds.group(0))

        return 0

    def _validate_mailto(self, text, pos):
        tail = text[pos:]

        if not self.re.get("mailto"):
            self.re["mailto"] = re.compile(
                "^" + self.re["src_email_name"] + "@" + self.re["src_host_strict"],
                flags=re.IGNORECASE,
            )

        founds = self.re["mailto"].search(tail)
        if founds:
            return len(founds.group(0))

        return 0

    def _reset_scan_cache(self):
        self._index = -1
        self._text_cache = ""

    def _create_validator(self, regex):
        def func(text, pos):
            tail = text[pos:]
            founds = regex.search(tail)
            if founds:
                return len(founds.group(0))

            return 0

        return func

    def _create_normalizer(self):
        def func(match):
            self._normalize(match)

        return func

    def _create_match(self, shift):
        match = Match(self, shift)
        self._compiled[match.schema]["normalize"](match)
        return match

    def __init__(self, schemas=None, options=None):
        self.default_options = {
            "fuzzy_link": True,
            "fuzzy_email": True,
            "fuzzy_ip": False,
        }

        self.default_schemas = {
            "http:": {"validate": self._validate_http},
            "https:": "http:",
            "ftp:": "http:",
            "//": {"validate": self._validate_double_slash},
            "mailto:": {"validate": self._validate_mailto},
        }

        # RE pattern for 2-character tlds (autogenerated by ./support/tlds_2char_gen.js)
        self.tlds_2ch_src_re = "a[cdefgilmnoqrstuwxz]|b[abdefghijmnorstvwyz]|c[acdfghiklmnoruvwxyz]|d[ejkmoz]|e[cegrstu]|f[ijkmor]|g[abdefghilmnpqrstuwy]|h[kmnrtu]|i[delmnoqrst]|j[emop]|k[eghimnprwyz]|l[abcikrstuvy]|m[acdeghklmnopqrstuvwxyz]|n[acefgilopruz]|om|p[aefghklmnrstwy]|qa|r[eosuw]|s[abcdeghijklmnortuvxyz]|t[cdfghjklmnortvwz]|u[agksyz]|v[aceginu]|w[fs]|y[et]|z[amw]"  # noqa: E501

        # DON'T try to make PRs with changes. Extend TLDs with LinkifyIt.tlds() instead
        self.tlds_default = "biz|com|edu|gov|net|org|pro|web|xxx|aero|asia|coop|info|museum|name|shop|рф".split(  # noqa: E501
            "|"
        )

        if options:
            self.default_options.update(options)
            self._opts = self.default_options
        else:
            self._opts = self.default_options

        # Cache last tested result. Used to skip repeating steps on next `match` call.
        self._index = -1
        self._last_index = -1  # Next scan position
        self._schema = ""
        self._text_cache = ""

        if schemas:
            self.default_schemas.update(schemas)
            self._schemas = self.default_schemas
        else:
            self._schemas = self.default_schemas

        self._compiled = {}

        self._tlds = self.tlds_default
        self._tlds_replaced = False

        self.re = {}

        self._compile()

    def _compile(self):
        """Schemas compiler. Build regexps."""

        # Load & clone RE patterns.
        # regex = copy.deepcopy(build_re(self._opts))
        # self.re = copy.deepcopy(build_re(self._opts))
        regex = self.re = build_re(self._opts)

        # Define dynamic patterns
        tlds = copy.deepcopy(self._tlds)

        self._on_compile()

        if not self._tlds_replaced:
            tlds.append(self.tlds_2ch_src_re)
        tlds.append(regex["src_xn"])

        regex["src_tlds"] = "|".join(tlds)

        def untpl(tpl):
            return tpl.replace("%TLDS%", regex["src_tlds"])

        regex["email_fuzzy"] = re.compile(
            untpl(regex["tpl_email_fuzzy"]), flags=re.IGNORECASE
        )
        regex["link_fuzzy"] = re.compile(
            untpl(regex["tpl_link_fuzzy"]), flags=re.IGNORECASE
        )
        regex["link_no_ip_fuzzy"] = re.compile(
            untpl(regex["tpl_link_no_ip_fuzzy"]), flags=re.IGNORECASE
        )
        regex["host_fuzzy_test"] = re.compile(
            untpl(regex["tpl_host_fuzzy_test"]), flags=re.IGNORECASE
        )

        #
        # Compile each schema
        #

        aliases = []

        self._compiled = {}

        for name, val in self._schemas.items():
            # skip disabled methods
            if val is None:
                continue

            compiled = {"validate": None, "link": None}

            self._compiled[name] = compiled

            if isinstance(val, dict):
                if isinstance(val.get("validate"), RE_TYPE):
                    compiled["validate"] = self._create_validator(val.get("validate"))
                elif isinstance(val.get("validate"), types.MethodType):
                    compiled["validate"] = val.get("validate")
                # Add custom handler
                elif isinstance(val.get("validate"), types.FunctionType):
                    setattr(LinkifyIt, "func", val.get("validate"))
                    compiled["validate"] = self.func
                else:
                    raise SchemaError(name, val)

                if isinstance(val.get("normalize"), types.MethodType):
                    compiled["normalize"] = val.get("normalize")
                # Add custom handler
                elif isinstance(val.get("normalize"), types.FunctionType):
                    setattr(LinkifyIt, "func", val.get("normalize"))
                    compiled["normalize"] = self.func
                elif not val.get("normalize"):
                    compiled["normalize"] = self._create_normalizer()
                else:
                    raise SchemaError(name, val)

                continue

            if isinstance(val, str):
                aliases.append(name)
                continue

            raise SchemaError(name, val)

        #
        # Compile postponed aliases
        #
        for alias in aliases:
            if not self._compiled.get(self._schemas.get(alias)):
                continue

            self._compiled[alias]["validate"] = self._compiled[self._schemas[alias]][
                "validate"
            ]
            self._compiled[alias]["normalize"] = self._compiled[self._schemas[alias]][
                "normalize"
            ]

        # Fake record for guessed links
        self._compiled[""] = {"validate": None, "normalize": self._create_normalizer()}

        #
        # Build schema condition
        #
        slist = "|".join(
            [
                escape_re(name)
                for name, val in self._compiled.items()
                if len(name) > 0 and val
            ]
        )

        re_schema_test = (
            "(^|(?!_)(?:[><\uff5c]|" + regex["src_ZPCc"] + "))(" + slist + ")"
        )

        # (?!_) cause 1.5x slowdown
        self.re["schema_test"] = re.compile(re_schema_test, flags=re.IGNORECASE)
        self.re["schema_search"] = re.compile(re_schema_test, flags=re.IGNORECASE)

        self.re["pretest"] = re.compile(
            "(" + re_schema_test + ")|(" + self.re["host_fuzzy_test"].pattern + ")|@",
            flags=re.IGNORECASE,
        )

        # Cleanup

        self._reset_scan_cache()

    def add(self, schema, definition):
        """Add new rule definition.

        See constructor description for details.

        Args:
            schema (str): rule name (fixed pattern prefix)
            definition (str or regex or object): schema definition
        """
        self._schemas[schema] = definition
        self._compile()
        return self

    def set(self, options):
        """Set recognition options for links without schema.

        Args:
            options (object): { fuzzyLink|fuzzyEmail|fuzzyIP: true|false }
        """
        self._opts.update(options)
        return self

    def test(self, text):
        """Searches linkifiable pattern and returns `true` on success or `false`
        on fail.

        Args:
            text (str): xxxxxx

        Returns:
            bool: xxxxxx
        """
        self._text_cache = text
        self._index = -1

        if not len(text):
            return False

        if self.re["schema_test"].search(text):
            regex = self.re["schema_search"]
            last_index = 0
            matched_iter = regex.finditer(text[last_index:])
            for matched in matched_iter:
                last_index = matched.end(0)
                m = (matched.group(), matched.groups()[0], matched.groups()[1])
                length = self.test_schema_at(text, m[2], last_index)
                if length:
                    self._schema = m[2]
                    self._index = matched.start(0) + len(m[1])
                    self._last_index = matched.start(0) + len(m[0]) + length
                    break

        if self._opts.get("fuzzy_link") and self._compiled.get("http:"):
            # guess schemaless links
            matched_tld = self.re["host_fuzzy_test"].search(text)
            if matched_tld:
                tld_pos = matched_tld.start(0)
            else:
                tld_pos = -1
            if tld_pos >= 0:
                # if tld is located after found link - no need to check fuzzy pattern
                if self._index < 0 or tld_pos < self._index:
                    if self._opts.get("fuzzy_ip"):
                        pattern = self.re["link_fuzzy"]
                    else:
                        pattern = self.re["link_no_ip_fuzzy"]

                    ml = pattern.search(text)
                    if ml:
                        shift = ml.start(0) + len(ml.groups()[0])

                        if self._index < 0 or shift < self._index:
                            self._schema = ""
                            self._index = shift
                            self._last_index = ml.start(0) + len(ml.group())

        if self._opts.get("fuzzy_email") and self._compiled.get("mailto:"):
            # guess schemaless emails
            at_pos = indexOf(text, "@")
            if at_pos >= 0:
                # We can't skip this check, because this cases are possible:
                # 192.168.1.1@gmail.com, my.in@example.com
                me = self.re["email_fuzzy"].search(text)
                if me:
                    shift = me.start(0) + len(me.groups()[0])
                    next_shift = me.start(0) + len(me.group())

                    if (
                        self._index < 0
                        or shift < self._index
                        or (shift == self._index and next_shift > self._last_index)
                    ):
                        self._schema = "mailto:"
                        self._index = shift
                        self._last_index = next_shift

        return self._index >= 0

    def pretest(self, text):
        """Very quick check, that can give false positives.

        Returns true if link MAY BE can exists. Can be used for speed optimization,
        when you need to check that link NOT exists.

        Args:
            text (str): xxxxxx

        Returns:
            bool: xxxxxx
        """
        if self.re["pretest"].search(text):
            return True

        return False

    def test_schema_at(self, text, name, position):
        """Similar to `~linkify_it.LinkifyIt.test` but checks only specific protocol
        tail exactly at given position. Returns length of found pattern (0 on fail).

        Args:
            text (str): text to scan
            name (str): rule (schema) name
            position (int): text offset to check from
        """
        # If not supported schema check requested - terminate
        if not self._compiled.get(name.lower()):
            return 0
        return self._compiled.get(name.lower()).get("validate")(text, position)
        # custom twitter API
        # return self._compiled.get(name.lower()).get("validate")(self, text, position)

    def match(self, text):
        """Returns array of found link descriptions or `null` on fail.

        We strongly recommend to use `~linkify_it.LinkifyIt.test` first, for best
        speed.

        Args:
            text (str):

        Returns:
            list or None: Result match description
                * **schema** - link schema, can be empty for fuzzy links, or `//`
                    for protocol-neutral  links.
                * **index** - offset of matched text
                * **lastIndex** - offset of matched text
                * **raw** - offset of matched text
                * **text** - normalized text
                * **url** - link, generated from matched text
        """
        shift = 0
        result = []

        # try to take previous element from cache, if .test() called before
        if self._index >= 0 and self._text_cache == text:
            result.append(self._create_match(shift))
            shift = self._last_index

        # Cut head if cache was used
        tail = text[shift:] if shift else text

        # Scan string until end reached
        while self.test(tail):
            result.append(self._create_match(shift))

            tail = tail[self._last_index :]
            shift += self._last_index

        if len(result):
            return result

        return None

    def tlds(self, list_tlds, keep_old=False):
        """Load (or merge) new tlds list.

        Those are user for fuzzy links (without prefix) to avoid false positives.
        By default this algorythm used:

        * hostname with any 2-letter root zones are ok.
        * biz|com|edu|gov|net|org|pro|web|xxx|aero|asia|coop|info|museum|name|shop|рф
            are ok.
        * encoded (`xn--...`) root zones are ok.

        If list is replaced, then exact match for 2-chars root zones will be checked.

        Args:
            list_tlds (list): list of tlds
            keep_old (bool): merge with current list if `true` (`false` by default)
        """
        _list = list_tlds if isinstance(list_tlds, list) else [list_tlds]

        if not keep_old:
            self._tlds = copy.copy(_list)
            self._tlds_replaced = True
            self._compile()
            return self

        self._tlds.extend(_list)
        self._tlds = sorted(list(set(self._tlds)), reverse=True)

        self._compile()
        return self

    def _normalize(self, match):
        """Default normalizer (if schema does not define it's own).

        Args:
            match ():
        """
        if not match.schema:
            match.url = "http://" + match.url

        if match.schema == "mailto:" and not re.search(
            "^mailto:", match.url, flags=re.IGNORECASE
        ):
            match.url = "mailto:" + match.url

    def _on_compile(self):
        """Override to modify basic RegExp-s."""
        pass
