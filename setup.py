import re
from os import path

import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

with open(path.join(path.dirname(__file__), "linkify_it", "__init__.py")) as f:
    match = re.search(r"__version__\s*=\s*[\'\"](.+?)[\'\"]", f.read())
    version = match.group(1)


setuptools.setup(
    name="linkify-it-py",
    version=version,
    license="MIT",
    author="tsutsu3",
    description="Links recognition library with FULL unicode support.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/tsutsu3/linkify-it-py",
    packages=setuptools.find_packages(exclude=["test", "benchmark"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.6",
    keywords=["linkify", "linkifier", "autolink", "autolinker"],
    install_requires=["uc-micro-py"],
    extras_require={
        "dev": ["pre-commit", "isort", "flake8", "black"],
        "test": ["coverage", "pytest", "pytest-cov"],
        "doc": ["sphinx", "sphinx_book_theme", "sphinx-rtd-theme"],
    },
)
