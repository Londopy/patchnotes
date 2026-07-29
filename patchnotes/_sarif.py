"""
patchnotes._sarif
SARIF 2.1.0 output for `patchnotes validate --format sarif`.

Upload the result with github/codeql-action/upload-sarif and changelog
problems appear in the repository's Security > Code scanning tab and as
PR annotations.
"""

from __future__ import annotations

from ._validation import Severity

_RULE_DESCRIPTIONS = {
    "PN101": "Date is not ISO 8601 (YYYY-MM-DD)",
    "PN102": "Duplicate version",
    "PN103": "Malformed release header",
    "PN104": "Entry outside any release block",
    "PN201": "Unknown change type section",
    "PN202": "Versions out of order",
    "PN203": "Empty release",
    "PN204": "No releases found",
    "PN205": "Version is not semver-like",
    "PN206": "Missing compare-link footnote",
    "PN207": "Orphaned compare-link footnote",
    "PN301": "YAML schema problem",
}


def to_sarif(issues: list, file: str, tool_version: str) -> dict:
    """Build a SARIF 2.1.0 document from validation issues."""
    uri = file.replace("\\", "/")
    rule_ids = sorted({i.code for i in issues} | set())
    rules = [
        {
            "id": rid,
            "shortDescription": {
                "text": _RULE_DESCRIPTIONS.get(rid, "Changelog issue")
            },
            "helpUri": "https://github.com/Londopy/patchnotes#validation-and-strict-mode",
        }
        for rid in rule_ids
    ]
    results = []
    for i in issues:
        result = {
            "ruleId": i.code,
            "level": "error" if i.severity is Severity.ERROR else "warning",
            "message": {"text": i.message},
        }
        location: dict = {"artifactLocation": {"uri": uri}}
        if i.line is not None:
            location["region"] = {"startLine": i.line}
        result["locations"] = [{"physicalLocation": location}]
        results.append(result)
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "patchnotes",
                        "informationUri": "https://github.com/Londopy/patchnotes",
                        "version": tool_version,
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }
