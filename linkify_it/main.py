import copy
import re
import types

from .ucre import build_re

# py>=37: re.Pattern, else: _sre.SRE_Pattern
RE_TYPE = type(re.compile(r""))


def _escape_re(string):
    return re.sub(r"([.?*+^$[\]\\(){}|-])", r"\\\1", string)


def _index_of(text, search_value):
    try:
        result = text.index(search_value)
    except ValueError:
        result = -1

    return result


def _at(candidates, position):
    """Item at ``position``, or ``None`` once the list is exhausted."""
    return candidates[position] if position < len(candidates) else None


def _choose(a, b):
    """Return whichever candidate should be emitted first.

    The earlier start wins; on equal starts the longer match wins. A full tie
    keeps ``a``, so the order the candidates are folded in sets the priority.
    ``None`` means the corresponding list has no candidate left.
    """
    if a is None:
        return b
    if b is None:
        return a
    if a.index != b.index:
        return a if a.index < b.index else b
    return a if a.last_index >= b.last_index else b


class SchemaError(Exception):
    """Linkify schema error"""

    def __init__(self, name, val):
        message = f"(LinkifyIt) Invalid schema '{name}': '{val}'"
        super().__init__(message)


class Match:
    """Match result.

    Attributes:
        schema (str): Prefix (protocol) for matched string.
        index (int): First position of matched string.
        last_index (int): Next position after matched string.
        raw (str): Matched string.
        text (str): Notmalized text of matched string.
        url (str): Normalized url of matched string.

    Args:
        text (str): text the match was found in
        schema (str): link schema, empty for fuzzy links
        index (int): first position of matched string
        last_index (int): next position after matched string
    """

    def __repr__(self):
        return (
            f"{self.__class__.__module__}.{self.__class__.__name__}({self.__dict__!r})"
        )

    def __init__(self, text, schema, index, last_index):
        raw = text[index:last_index]

        self.schema = schema.lower()
        self.index = index
        self.last_index = last_index
        self.raw = raw
        self.text = raw
        self.url = raw


class _Candidate:
    """A single hit found by one of the scan passes of :meth:`LinkifyIt.match`.

    Every pass collects all of its hits up front, so no pass ever rescans a tail
    that an earlier one already walked.

    Args:
        schema (str): link schema, empty for fuzzy links
        index (int): first position of matched string
        last_index (int): next position after matched string
    """

    __slots__ = ("index", "last_index", "schema")

    def __init__(self, schema, index, last_index):
        self.schema = schema
        self.index = index
        self.last_index = last_index


class LinkifyIt:
    """Creates new linkifier instance with optional additional schemas.

    By default understands:

    - ``http(s)://...`` , ``ftp://...``, ``mailto:...`` & ``//...`` links
    - "fuzzy" links and emails (example.com, foo@bar.com).

    ``schemas`` is an dict where each key/value describes protocol/rule:

    - **key** - link prefix (usually, protocol name with ``:`` at the end, ``skype:``
      for example). `linkify-it` makes shure that prefix is not preceeded with
      alphanumeric char. Only whitespaces and punctuation allowed.

    - **value** - rule to check tail after link prefix

      - *str* - just alias to existing rule
      - *dict*

        - *validate* - either a ``re.Pattern``, ``re str`` (start with ``^``, and don't
          include the link prefix itself), or a validator ``function`` which, given
          arguments *self*, *text* and *pos* returns the length of a match in *text*
          starting at index *pos*. *pos* is the index right after the link prefix.
        - *normalize* - optional function to normalize text & url of matched
          result (for example, for @twitter mentions).

    ``options`` is an dict:

    - **fuzzyLink** - recognige URL-s without ``http(s):`` prefix. Default ``True``.
    - **fuzzyIP** - allow IPs in fuzzy links above. Can conflict with some texts
      like version numbers. Default ``False``.
    - **fuzzyEmail** - recognize emails without ``mailto:`` prefix.
    - **---** - set `True` to terminate link with `---` (if it's considered as long
      dash).

    Args:
        schemas (dict): Optional. Additional schemas to validate (prefix/validator)
        options (dict): { fuzzy_link | fuzzy_email | fuzzy_ip: True | False }.
            Default: {"fuzzy_link": True, "fuzzy_email": True, "fuzzy_ip": False}.
    """

    # The built-in validators match at `pos` with a compiled pattern rather than
    # running an `^`-anchored search over `text[pos:]` the way upstream does.
    # The slice is an O(n) copy, and Python 3.10 does not apply the `^` anchor
    # optimization, so `re.search` rescans the whole tail -- together that is
    # quadratic on inputs like `mailto:mailto:...`. Schemas registered through
    # `add()` keep the sliced form: their patterns are documented to start
    # with `^`, which cannot match at a non-zero position.

    def _validate_http(self, text, pos):
        if not self.re.get("http"):
            # compile lazily, because "host"-containing variables can change on
            # tlds update.
            self.re["http"] = re.compile(
                "\\/\\/"
                + self.re["src_auth"]
                + self.re["src_host_port_strict"]
                + self.re["src_path"],
                flags=re.IGNORECASE,
            )

        founds = self.re["http"].match(text, pos)
        if founds:
            return len(founds.group())

        return 0

    def _validate_double_slash(self, text, pos):
        if not self.re.get("not_http"):
            # compile lazily, because "host"-containing variables can change on
            # tlds update.
            self.re["not_http"] = re.compile(
                self.re["src_auth"]
                + "(?:localhost|(?:(?:"
                + self.re["src_domain"]
                + ")\\.)+"
                + self.re["src_domain_root"]
                + ")"
                + self.re["src_port"]
                + self.re["src_host_terminator"]
                + self.re["src_path"],
                flags=re.IGNORECASE,
            )

        founds = self.re["not_http"].match(text, pos)
        if founds:
            if pos >= 3 and text[pos - 3] == ":":
                return 0

            if pos >= 3 and text[pos - 3] == "/":
                return 0

            return len(founds.group(0))

        return 0

    def _validate_mailto(self, text, pos):
        if not self.re.get("mailto"):
            self.re["mailto"] = re.compile(
                self.re["src_email_name"] + "@" + self.re["src_host_strict"],
                flags=re.IGNORECASE,
            )

        founds = self.re["mailto"].match(text, pos)
        if founds:
            return len(founds.group(0))

        return 0

    def _create_validator(self, regex):
        def func(text, pos):
            tail = text[pos:]
            if isinstance(regex, str):
                founds = re.search(regex, tail, flags=re.IGNORECASE)
            else:
                # re.Pattern
                founds = re.search(regex, tail)

            if founds:
                return len(founds.group(0))

            return 0

        return func

    def _create_normalizer(self):
        def func(match):
            self.normalize(match)

        return func

    def _create_match(self, text, schema, index, last_index):
        match = Match(text, schema, index, last_index)
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
        self.re = build_re(self._opts)

        # Define dynamic patterns
        tlds = copy.deepcopy(self._tlds)

        self._on_compile()

        if not self._tlds_replaced:
            tlds.append(self.tlds_2ch_src_re)
        tlds.append(self.re["src_xn"])

        self.re["src_tlds"] = "|".join(tlds)

        def untpl(tpl):
            return tpl.replace("%TLDS%", self.re["src_tlds"])

        self.re["email_fuzzy"] = untpl(self.re["tpl_email_fuzzy"])

        self.re["link_fuzzy"] = untpl(self.re["tpl_link_fuzzy"])

        self.re["link_no_ip_fuzzy"] = untpl(self.re["tpl_link_no_ip_fuzzy"])

        self.re["host_fuzzy_test"] = untpl(self.re["tpl_host_fuzzy_test"])

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
                elif isinstance(val.get("validate"), str):
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
                _escape_re(name)
                for name, val in self._compiled.items()
                if len(name) > 0 and val
            ]
        )

        re_schema_test = (
            "(^|(?!_)(?:[><\uff5c]|" + self.re["src_ZPCc"] + "))(" + slist + ")"
        )

        # (?!_) cause 1.5x slowdown
        self.re["schema_test"] = re_schema_test
        self.re["schema_search"] = re_schema_test
        self.re["schema_at_start"] = "^" + self.re["schema_search"]

        self.re["pretest"] = (
            "(" + re_schema_test + ")|(" + self.re["host_fuzzy_test"] + ")|@"
        )

    def add(self, schema, definition):
        """Add new rule definition. (chainable)

        See :class:`linkify_it.main.LinkifyIt` init description for details.
        ``schema`` is a link prefix (``skype:``, for example), and ``definition``
        is a ``str`` to alias to another schema, or an ``dict`` with ``validate`` and
        optionally `normalize` definitions. To disable an existing rule, use
        ``.add(<schema>, None)``.

        Args:
            schema (str): rule name (fixed pattern prefix)
            definition (`str` or `re.Pattern`): schema definition

        Return:
            :class:`linkify_it.main.LinkifyIt`
        """
        self._schemas[schema] = definition
        self._compile()
        return self

    def set(self, options):
        """Override default options. (chainable)

        Missed properties will not be changed.

        Args:
            options (dict): ``keys``: [``fuzzy_link`` | ``fuzzy_email`` | ``fuzzy_ip``].
                ``values``: [``True`` | ``False``]

        Return:
            :class:`linkify_it.main.LinkifyIt`
        """
        self._opts.update(options)
        return self

    def test(self, text):
        """Searches linkifiable pattern and returns ``True`` on success or ``False``
        on fail.

        Args:
            text (str): text to search

        Returns:
            bool: ``True`` if a linkable pattern was found, otherwise it is ``False``.
        """
        if not len(text):
            return False

        if re.search(self.re["schema_test"], text, flags=re.IGNORECASE):
            matched_iter = re.finditer(
                self.re["schema_search"], text, flags=re.IGNORECASE
            )
            for matched in matched_iter:
                if self.test_schema_at(text, matched.group(2), matched.end(0)):
                    return True

        if self._opts.get("fuzzy_link") and self._compiled.get("http:"):
            # guess schemaless links
            if re.search(self.re["host_fuzzy_test"], text, flags=re.IGNORECASE):
                if self._opts.get("fuzzy_ip"):
                    pattern = self.re["link_fuzzy"]
                else:
                    pattern = self.re["link_no_ip_fuzzy"]

                if re.search(pattern, text, flags=re.IGNORECASE):
                    return True

        if self._opts.get("fuzzy_email") and self._compiled.get("mailto:"):
            # guess schemaless emails
            at_pos = _index_of(text, "@")
            if at_pos >= 0:
                # We can't skip this check, because this cases are possible:
                # 192.168.1.1@gmail.com, my.in@example.com
                if re.search(self.re["email_fuzzy"], text, flags=re.IGNORECASE):
                    return True

        return False

    def pretest(self, text):
        """Very quick check, that can give false positives.

        Returns true if link MAY BE can exists. Can be used for speed optimization,
        when you need to check that link NOT exists.

        Args:
            text (str): text to search

        Returns:
            bool: ``True`` if a linkable pattern was found, otherwise it is ``False``.
        """
        if re.search(self.re["pretest"], text, flags=re.IGNORECASE):
            return True

        return False

    def test_schema_at(self, text, name, position):
        """Similar to :meth:`linkify_it.main.LinkifyIt.test` but checks only
        specific protocol tail exactly at given position.

        Args:
            text (str): text to scan
            name (str): rule (schema) name
            position (int): length of found pattern (0 on fail).

        Returns:
            int: text (str): text to search
        """
        # If not supported schema check requested - terminate
        if not self._compiled.get(name.lower()):
            return 0
        return self._compiled.get(name.lower()).get("validate")(text, position)

    def match(self, text):
        """Returns ``list`` of found link descriptions or ``None`` on fail.

        We strongly recommend to use :meth:`linkify_it.main.LinkifyIt.test`
        first, for best speed.

        Args:
            text (str): text to search

        Returns:
            ``list`` or ``None``: Result match description:
                * **schema** - link schema, can be empty for fuzzy links, or ``//``
                  for protocol-neutral  links.
                * **index** - offset of matched text
                * **last_index** - offset of matched text
                * **raw** - offset of matched text
                * **text** - normalized text
                * **url** - link, generated from matched text
        """
        if not len(text):
            return None

        # Collect every hit of each pattern in one pass over the whole text.
        schemed = []
        fuzzy_link = []
        fuzzy_email = []

        # scan for links with schema
        if re.search(self.re["schema_test"], text, flags=re.IGNORECASE):
            matched_iter = re.finditer(
                self.re["schema_search"], text, flags=re.IGNORECASE
            )
            for matched in matched_iter:
                length = self.test_schema_at(text, matched.group(2), matched.end(0))
                if length:
                    schemed.append(
                        _Candidate(
                            matched.group(2),
                            matched.start(0) + len(matched.group(1)),
                            matched.start(0) + len(matched.group(0)) + length,
                        )
                    )

        if self._opts.get("fuzzy_link") and self._compiled.get("http:"):
            # guess schemaless links
            if self._opts.get("fuzzy_ip"):
                pattern = self.re["link_fuzzy"]
            else:
                pattern = self.re["link_no_ip_fuzzy"]

            for matched in re.finditer(pattern, text, flags=re.IGNORECASE):
                fuzzy_link.append(
                    _Candidate(
                        "",
                        matched.start(0) + len(matched.group(1)),
                        matched.start(0) + len(matched.group(0)),
                    )
                )

        if self._opts.get("fuzzy_email") and self._compiled.get("mailto:"):
            # guess schemaless emails
            matched_iter = re.finditer(
                self.re["email_fuzzy"], text, flags=re.IGNORECASE
            )
            for matched in matched_iter:
                fuzzy_email.append(
                    _Candidate(
                        "mailto:",
                        matched.start(0) + len(matched.group(1)),
                        matched.start(0) + len(matched.group(0)),
                    )
                )

        # Merge the three streams, which are each already sorted by position,
        # dropping candidates that overlap a match already emitted.
        indexes = [0, 0, 0]
        result = []
        last_index = 0

        while True:
            candidates = [
                _at(schemed, indexes[0]),
                _at(fuzzy_email, indexes[1]),
                _at(fuzzy_link, indexes[2]),
            ]

            candidate = _choose(_choose(candidates[0], candidates[1]), candidates[2])

            if candidate is None:
                break

            if candidate is candidates[0]:
                indexes[0] += 1
            elif candidate is candidates[1]:
                indexes[1] += 1
            else:
                indexes[2] += 1

            if candidate.index < last_index:
                continue

            result.append(
                self._create_match(
                    text, candidate.schema, candidate.index, candidate.last_index
                )
            )
            last_index = candidate.last_index

        if len(result):
            return result

        return None

    def match_at_start(self, text):
        """Returns fully-formed (not fuzzy) link if it starts at the beginning
        of the string, and null otherwise.

        Args:
            text (str): text to search

        Retuns:
            ``Match`` or ``None``
        """
        if not len(text):
            return None

        founds = re.search(self.re["schema_at_start"], text, flags=re.IGNORECASE)
        if not founds:
            return None

        length = self.test_schema_at(text, founds.group(2), len(founds.group(0)))
        if not length:
            return None

        return self._create_match(
            text,
            founds.group(2),
            founds.start(0) + len(founds.group(1)),
            founds.start(0) + len(founds.group(0)) + length,
        )

    def tlds(self, list_tlds, keep_old=False):
        """Load (or merge) new tlds list. (chainable)

        Those are user for fuzzy links (without prefix) to avoid false positives.
        By default this algorythm used:

        * hostname with any 2-letter root zones are ok.
        * biz|com|edu|gov|net|org|pro|web|xxx|aero|asia|coop|info|museum|name|shop|рф
          are ok.
        * encoded (`xn--...`) root zones are ok.

        If list is replaced, then exact match for 2-chars root zones will be checked.

        Args:
            list_tlds (list or str): ``list of tlds`` or ``tlds string``
            keep_old (bool): merge with current list if q`True`q (q`Falseq` by default)
        """
        _list = list_tlds if isinstance(list_tlds, list) else [list_tlds]

        if not keep_old:
            self._tlds = _list
            self._tlds_replaced = True
            self._compile()
            return self

        self._tlds.extend(_list)
        self._tlds = sorted(list(set(self._tlds)), reverse=True)

        self._compile()
        return self

    def normalize(self, match):
        """Default normalizer (if schema does not define it's own).

        Args:
            match (:class:`linkify_it.main.Match`): Match result
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
