"""Inputs that used to make the scan loop degrade to O(n^2)."""

import pytest

from linkify_it import LinkifyIt

TIMEOUT_SECONDS = 10


@pytest.mark.timeout(TIMEOUT_SECONDS)
def test_should_not_hang_on_fuzzy_links_followed_by_an_email_marker():
    # ~1 MiB input
    LinkifyIt().match("a.com " * 174762 + "@")


@pytest.mark.timeout(TIMEOUT_SECONDS)
def test_should_not_hang_on_fuzzy_emails_followed_by_a_link_marker():
    # ~1 MiB input
    LinkifyIt().match("a@b.com " * 131071 + ".com")
