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


@pytest.mark.timeout(TIMEOUT_SECONDS)
def test_should_not_hang_on_repeated_mailto_schema_prefixes():
    # ~680 KiB input. The ":" in mailto's prefix is also a valid email-name
    # char, so "mailto:mailto:..." chains into O(n) schema hits, each running
    # the mailto validator to the end of the tail => O(n^2) without a fix.
    LinkifyIt().match("mailto:" * 100000)
