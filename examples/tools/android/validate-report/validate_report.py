#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validate Report Tool — generate a Markdown validation report.

Usage:
    python validate_report.py <results_file> <output_path>

    results_file: path to the flow.foreach results JSON file
                  ({"count", "passed_count", "failed_count", "all_passed", "results"}).
    output_path:  path to write the Markdown report to.

Prints a single-line JSON summary object to stdout and exits 0 on success:
    {"report_path": "<absolute path>", "passed_count": N, "failed_count": N, "all_passed": bool}
"""

import json
import os
import sys


def _cell(text):
    """Escape a Markdown table cell (pipe characters and newlines)."""
    return str(text).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def main(argv):
    results_file = argv[0] if len(argv) > 0 else ""
    output_path = argv[1] if len(argv) > 1 else ""

    with open(results_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = int(data.get("count", 0))
    passed_count = int(data.get("passed_count", 0))
    failed_count = int(data.get("failed_count", 0))
    all_passed = bool(data.get("all_passed", failed_count == 0))
    results = data.get("results", [])

    lines = []
    lines.append("# APK Validation Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total**: {count}")
    lines.append(f"- **Passed**: {passed_count}")
    lines.append(f"- **Failed**: {failed_count}")
    lines.append(f"- **All Passed**: {'Yes' if all_passed else 'No'}")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append("| Name | Type | Result | Actual | Expected | Message |")
    lines.append("|---|---|---|---|---|---|")

    for result in results:
        item = result.get("item") or {}
        outputs = result.get("outputs") or {}
        error = result.get("error")

        name = outputs.get("name") or item.get("name") or "?"
        entry_type = outputs.get("type") or item.get("type") or "?"

        passed = bool(outputs.get("passed", False))
        if error:
            passed = False

        actual = outputs.get("actual", "") or ""
        expected = outputs.get("expected", "") or ""
        message = error or outputs.get("message", "") or ""

        result_cell = "PASS" if passed else "FAIL"
        lines.append(
            "| {} | {} | {} | {} | {} | {} |".format(
                _cell(name),
                _cell(entry_type),
                result_cell,
                _cell(actual),
                _cell(expected),
                _cell(message),
            )
        )

    report = "\n".join(lines) + "\n"

    abs_output = os.path.abspath(output_path)
    parent = os.path.dirname(abs_output) or "."
    os.makedirs(parent, exist_ok=True)
    with open(abs_output, "w", encoding="utf-8") as f:
        f.write(report)

    return {
        "report_path": abs_output,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "all_passed": all_passed,
    }


if __name__ == "__main__":
    argv = sys.argv[1:]
    try:
        result = main(argv)
    except Exception as exc:
        result = {
            "report_path": "",
            "passed_count": 0,
            "failed_count": 0,
            "all_passed": False,
            "error": f"error: {exc}",
        }
    print(json.dumps(result))
    sys.exit(0)
