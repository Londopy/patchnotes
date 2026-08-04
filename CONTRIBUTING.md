# Contributing to patchnotes

Contributions are welcome — bug reports, format parsers, validation rules,
documentation fixes, and questions about how the parser handles a particular
changelog all help.

## Reporting a bug

Open an issue at
<https://github.com/Londopy/patchnotes/issues> and include:

- the version of patchnotes (`patchnotes --version`) and your Python version;
- the smallest changelog snippet that reproduces the problem;
- what you expected to happen, and what happened instead.

Changelogs in the wild are extremely varied, and a real off-specification file
that patchnotes mishandles is one of the most useful things you can send. If
the file is public, a link to it is enough.

## Suggesting a feature

Open an issue describing the problem you are trying to solve before writing
code. patchnotes deliberately keeps a small dependency footprint (PyYAML only)
and a stable public API, so feature discussions usually turn on whether
something belongs in the core, in a pluggable format parser, or in the CLI.

## Development setup

```bash
git clone https://github.com/Londopy/patchnotes.git
cd patchnotes
pip install -e ".[mkdocs]"
pip install pytest mypy types-PyYAML
```

Install the `mkdocs` extra even if you are not touching the documentation
plugin: without it, `tests/test_v24.py` skips the whole module (you will see
`163 passed, 1 skipped` instead of `180 passed`).

Run the test suite:

```bash
pytest -q
```

Type-check (the project is checked under `mypy --strict`, and must stay clean
both with and without the optional `mkdocs` extra installed):

```bash
mypy patchnotes
```

## Pull requests

1. Fork the repository and create a branch off `main`.
2. Add tests. Every parser change needs at least one test showing the new
   behaviour, and every new validation rule needs a test asserting both the
   issue code and the reported line number.
3. Keep the public API stable. Anything exported from `patchnotes/__init__.py`
   is public; breaking it requires a major version bump.
4. Add a changelog entry. The project uses its own fragment mechanism:

   ```bash
   patchnotes fragment add fixed "Handle CRLF line endings in YAML changelogs"
   ```

   This writes a file under `changelog.d/`, which avoids merge conflicts on
   `CHANGELOG.md` and is folded into the release at bump time.
5. Make sure `pytest -q` and `mypy patchnotes` both pass. CI runs the test
   suite on Python 3.10 and 3.13, strict-validates the project's own changelog
   using the bundled GitHub Action, and uploads validation results as SARIF.

## Adding a format parser

New changelog formats do not require changes to the core. Subclass
`FormatParser`, implement `parse`, and register it:

```python
from patchnotes import Changelog, FormatParser, register_format

class MyFormat(FormatParser):
    name = "myformat"
    extensions = (".mycl",)

    def parse(self, text: str) -> Changelog:
        ...
```

Format parsers must be lenient: record problems on `changelog.issues` using an
appropriate `ValidationIssue` code rather than raising. Strict mode is applied
by the caller, not by the parser.

## Validation rule conventions

Diagnostic codes are stable and are treated as public API, because users grep
for them in CI logs. When adding one:

- `PN1xx` — errors: a specification violation where data was lost or guessed.
- `PN2xx` — warnings: off-standard but recoverable.
- `PN3xx` — schema problems in structured (YAML) input.

Use the next free number in the range, add the code and a one-line description
to `_sarif.py` so it appears in code-scanning output, and never renumber an
existing code.

## Code of conduct

Be civil and assume good faith. Harassment of any kind is not acceptable, and
maintainers may close or block interactions that are abusive.

## Licence

By contributing you agree that your contributions are licensed under the MIT
Licence, the same terms that cover the rest of the project.
