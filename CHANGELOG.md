# Change Log

## v2.1.1 (2026-08-25)

Security release: `LinkifyIt.match()` was quadratic on untrusted input when linkify is enabled ([GHSA-8m2q-wq3r-6hq8](https://github.com/tsutsu3/linkify-it-py/security/advisories/GHSA-8m2q-wq3r-6hq8)).

- Fix quadratic complexity in `LinkifyIt.match()`, port of linkify-it 5.0.1 and 5.0.2 (upstream [CVE-2026-48801](https://github.com/advisories/GHSA-22p9-wv53-3rq4), [CVE-2026-59887](https://github.com/advisories/GHSA-v245-v573-v5vm)) ([#82](https://github.com/tsutsu3/linkify-it-py/pull/82))
- Match validators at a position instead of slicing the tail, needed because Python 3.10 does not optimize the `^` anchor ([#82](https://github.com/tsutsu3/linkify-it-py/pull/82))
- Allow `;` in the email name, matching linkify-it. **Behavior change**: `a;b@example.com` is now linkified ([#82](https://github.com/tsutsu3/linkify-it-py/pull/82))
- Update port.yml (linkify-it v5.0.2) ([#82](https://github.com/tsutsu3/linkify-it-py/pull/82))

## v2.1.0 (2026-03-01)

- Drop support for EOL Python 3.7, 3.8 ([bd78752](https://github.com/tsutsu3/linkify-it-py/commit/bd78752))
- Drop support for EOL Python 3.9 ([#75](https://github.com/tsutsu3/linkify-it-py/pull/75)) by [@hugovk](https://github.com/hugovk)
- Add support for Python 3.14 ([#75](https://github.com/tsutsu3/linkify-it-py/pull/75)) by [@hugovk](https://github.com/hugovk)
- Migrate to OIDC trusted publishing for PyPI and TestPyPI ([#77](https://github.com/tsutsu3/linkify-it-py/pull/77))
- Add workflow permissions for security hardening ([#77](https://github.com/tsutsu3/linkify-it-py/pull/77))
- Bump GitHub Actions dependencies ([#71](https://github.com/tsutsu3/linkify-it-py/pull/71), [#73](https://github.com/tsutsu3/linkify-it-py/pull/73))

## v2.0.3 (2024-02-04)

- Update port.yml (linkify-it v5.0.0) ([#54](https://github.com/tsutsu3/linkify-it-py/pull/54))
- Fix rtd ([#52](https://github.com/tsutsu3/linkify-it-py/pull/52))
- Add linkify-it-py-demo url ([#51](https://github.com/tsutsu3/linkify-it-py/pull/51))
- Fix package build ([#49](https://github.com/tsutsu3/linkify-it-py/pull/49))

## v2.0.2 (2023-05-02)

- Fix missing files to the test ([#44](https://github.com/tsutsu3/linkify-it-py/pull/44))

## v2.0.1 (2023-05-02)

- Update development tools
- Fix sdist is missing tests

## v2.0.0 (2022-05-07)

- Add `matchAtStart` method to match full URLs at the start of the string.
- Fixed paired symbols (`()`, `{}`, `""`, etc.) after punctuation.
- `---` option now affects parsing of emails  (e.g. `user@example.com---`)

## v1.0.3 (2021-12-18)

- Fixed [#98](https://github.com/markdown-it/linkify-it/issues/98). Don't count `;` at the end of link (when followed with space).

## v1.0.2 (2021-10-09)

- Fix: Schema key containing - not producing matches (#26)

## v1.0.1 (2020-12-18)

- Add manifest
- Add codecov.yml

## v1.0.0 (2020-11-15)

- First release
