from pathlib import Path

import pytest

from linkify_it import LinkifyIt

SAMPLES_PATH = Path(__file__).parent / "samples"


def read_samples(path):
    filenames = path.glob("**/*.txt")
    return sorted(list(filenames))


def get_ids(path):
    filenames = path.glob("**/*.txt")
    return [x.name for x in filenames]


@pytest.mark.parametrize(
    "filename", read_samples(SAMPLES_PATH), ids=get_ids(SAMPLES_PATH)
)
def test_init(benchmark, filename):
    benchmark(LinkifyIt)


@pytest.mark.parametrize(
    "filename", read_samples(SAMPLES_PATH), ids=get_ids(SAMPLES_PATH)
)
def test_pretest(benchmark, filename):
    linkify = LinkifyIt()

    path = Path(filename)
    text = path.read_text()

    benchmark(linkify.pretest, text)


@pytest.mark.parametrize(
    "filename", read_samples(SAMPLES_PATH), ids=get_ids(SAMPLES_PATH)
)
def test_test(benchmark, filename):
    linkify = LinkifyIt()

    path = Path(filename)
    text = path.read_text()

    benchmark(linkify.test, text)


@pytest.mark.parametrize(
    "filename", read_samples(SAMPLES_PATH), ids=get_ids(SAMPLES_PATH)
)
def test_match(benchmark, filename):
    linkify = LinkifyIt()

    path = Path(filename)
    text = path.read_text()

    benchmark(linkify.match, text)
