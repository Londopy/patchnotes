"""
tests/test_rst.py
Tests for the reStructuredText changelog parser.
"""

import pytest

from patchnotes import ChangeType, parse
from patchnotes.formats import detect_format, get_format
from patchnotes.formats.rst import strip_inline

BASIC = """\
Release History
===============

2.32.0 (2024-05-20)
-------------------

Security
~~~~~~~~

- Fixed a certificate verification issue

Added
~~~~~

- Support for HTTP/3

2.31.0 (2023-05-22)
-------------------

Fixed
~~~~~

- Small bug
"""

OVERLINE = """\
=========
Changelog
=========

1.1.0
=====

- Did a thing

1.0.0
=====

- Initial release
"""

TOWNCRIER = """\
Changelog
=========

.. towncrier release notes start

3.9.0 (2024-02-01)
------------------

Bugfixes
~~~~~~~~

- Fixed the thing (`#1234 <https://github.com/x/y/issues/1234>`_)

.. note::

   This directive body must not become an entry.

- Second entry
"""

NO_VERSIONS = """\
Contributing
============

Some prose.

Guidelines
----------

- Be nice
"""


class TestSectionParsing:
    def test_releases_and_dates(self):
        cl = parse(BASIC, filename="CHANGES.rst")
        assert [r.version for r in cl.releases] == ["2.32.0", "2.31.0"]
        assert str(cl.get_version("2.32.0").release_date) == "2024-05-20"

    def test_title_is_not_a_release(self):
        cl = parse(BASIC, filename="CHANGES.rst")
        assert cl.title == "Release History"

    def test_change_types_from_subsections(self):
        r = parse(BASIC, filename="CHANGES.rst").get_version("2.32.0")
        assert r.entries[0].change_type is ChangeType.SECURITY
        assert r.entries[0].text == "Fixed a certificate verification issue"
        assert any(e.change_type is ChangeType.ADDED for e in r.entries)

    def test_overline_titles(self):
        cl = parse(OVERLINE, filename="CHANGELOG.rst")
        assert [r.version for r in cl.releases] == ["1.1.0", "1.0.0"]
        assert cl.get_version("1.0.0").entries[0].text == "Initial release"

    def test_clean_file_validates_clean(self):
        assert parse(BASIC, filename="CHANGES.rst").is_valid(strict=True)


class TestDirectivesAndMarkup:
    def test_directive_bodies_are_not_entries(self):
        r = parse(TOWNCRIER, filename="CHANGES.rst").get_version("3.9.0")
        texts = [e.text for e in r.entries]
        assert "This directive body must not become an entry." not in texts
        assert "Second entry" in texts

    def test_towncrier_marker_ignored(self):
        cl = parse(TOWNCRIER, filename="CHANGES.rst")
        assert [r.version for r in cl.releases] == ["3.9.0"]

    @pytest.mark.parametrize("raw,expected", [
        ("``code``", "code"),
        ("**bold**", "bold"),
        ("*em*", "em"),
        ("`text <https://example.com>`_", "text"),
        (":issue:`42`", "42"),
        (":ref:`the docs <guide>`", "the docs"),
        ("a  b\n c", "a b c"),
    ])
    def test_strip_inline(self, raw, expected):
        assert strip_inline(raw) == expected


class TestDetection:
    def test_extension_wins(self):
        assert detect_format("whatever", "CHANGES.rst").name == "rst"

    def test_sniffs_real_rst(self):
        assert get_format("rst").sniff(TOWNCRIER)

    def test_does_not_steal_setext_markdown(self):
        """Setext-underlined markdown must stay with the markdown parser.

        The two are indistinguishable by adornments alone, and markdown
        already handles this shape — rerouting it would change results for
        existing documents.
        """
        setext = (
            "Release History\n===============\n\n"
            "2.32.0 (2024-05-20)\n-------------------\n\n"
            "### Security\n- Fixed cert verification issue\n"
        )
        assert not get_format("rst").sniff(setext)
        assert detect_format(setext, None).name == "markdown"


class TestDegradedInput:
    def test_no_version_sections_reports_and_recovers(self):
        cl = parse(NO_VERSIONS, filename="CHANGES.rst")
        assert cl.releases == []
        assert any(i.code == "PN204" for i in cl.validate())

    def test_empty_document(self):
        cl = parse("", filename="CHANGES.rst")
        assert cl.releases == []
        assert cl.validate()

    def test_never_raises_on_garbage(self):
        for junk in ("\x00\x01", "=" * 500, "- orphan bullet\n", "a\n=\n" * 50):
            parse(junk, filename="CHANGES.rst")
