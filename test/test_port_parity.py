"""Links that linkify-it recognizes but this port did not, due to port bugs.

Kept apart from test_linkify.py so that upstream's own fixtures stay byte
identical with linkify-it and remain diffable on the next port.
"""

from pathlib import Path

import pytest

from linkify_it import LinkifyIt

from .utils import read_fixture_file

FIXTURE_PATH = Path(__file__).parent / "fixtures"


def dummy(_):
    pass


@pytest.mark.parametrize(
    "number,line,expected",
    read_fixture_file(FIXTURE_PATH.joinpath("port_links.txt")),
)
def test_port_links(number, line, expected):
    linkifyit = LinkifyIt(options={"fuzzy_ip": True})

    linkifyit.normalize = dummy

    assert linkifyit.pretest(line) is True
    assert linkifyit.test("\n" + line + "\n") is True
    assert linkifyit.test(line) is True
    assert linkifyit.match(line)[0].url == expected
