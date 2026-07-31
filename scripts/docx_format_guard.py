#!/usr/bin/env python3
"""Create and verify format-preservation baselines for existing DOCX files."""

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from xml.etree import ElementTree as ET

SCHEMA_VERSION = 1
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "v": "urn:schemas-microsoft-com:vml",
}


def qn(prefix: str, local_name: str) -> str:
    return "{%s}%s" % (NS[prefix], local_name)


FORMAT_RULES = {
    qn("w", "pPr"): ("paragraph_properties", "subtree", False),
    qn("w", "rPr"): ("run_properties", "subtree", False),
    qn("w", "tblPr"): ("table_properties", "subtree", False),
    qn("w", "tblGrid"): ("table_grid", "subtree", False),
    qn("w", "trPr"): ("table_row_properties", "subtree", False),
    qn("w", "tcPr"): ("table_cell_properties", "subtree", False),
    qn("w", "sdtPr"): ("content_control_properties", "subtree", False),
    qn("w", "sectPr"): ("section_page_properties", "subtree", True),
    qn("wp", "extent"): ("drawing_extent", "subtree", False),
    qn("wp", "effectExtent"): ("drawing_effect_extent", "subtree", False),
    qn("wp", "positionH"): ("drawing_horizontal_position", "subtree", False),
    qn("wp", "positionV"): ("drawing_vertical_position", "subtree", False),
    qn("wp", "wrapNone"): ("drawing_wrap_none", "subtree", False),
    qn("wp", "wrapSquare"): ("drawing_wrap_square", "subtree", False),
    qn("wp", "wrapTight"): ("drawing_wrap_tight", "subtree", False),
    qn("wp", "wrapThrough"): ("drawing_wrap_through", "subtree", False),
    qn("wp", "wrapTopAndBottom"): ("drawing_wrap_top_bottom", "subtree", False),
    qn("wp", "inline"): ("drawing_inline_attributes", "attributes", False),
    qn("wp", "anchor"): ("drawing_anchor_attributes", "attributes", False),
    qn("a", "xfrm"): ("drawing_transform", "subtree", False),
    qn("v", "shape"): ("legacy_shape_attributes", "attributes", False),
}

W_BR = qn("w", "br")
W_TYPE = qn("w", "type")
VOLATILE_ATTRIBUTE_LOCALS = {
    "rsidR",
    "rsidRDefault",
    "rsidRPr",
    "rsidDel",
    "rsidP",
    "paraId",
    "textId",
    "anchorId",
    "editId",
}
PROTECTED_EXACT_PARTS = {
    "word/styles.xml",
    "word/stylesWithEffects.xml",
    "word/fontTable.xml",
    "word/settings.xml",
    "word/webSettings.xml",
    "word/numbering.xml",
}
PROTECTED_PART_RE = re.compile(r"^word/(?:header|footer)\d+\.xml$")


class GuardError(Exception):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_part_name(name: str) -> str:
    return name.replace("\\", "/")


def is_protected_part(name: str) -> bool:
    return (
        name in PROTECTED_EXACT_PARTS
        or name.startswith("word/theme/")
        or bool(PROTECTED_PART_RE.match(name))
    )


def load_package(path: Path) -> Dict[str, bytes]:
    if not path.is_file():
        raise GuardError("DOCX file does not exist: %s" % path)

    try:
        with zipfile.ZipFile(str(path), "r") as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            total_size = sum(info.file_size for info in infos)
            if total_size > MAX_UNCOMPRESSED_BYTES:
                raise GuardError(
                    "DOCX expands beyond the %d MiB safety limit"
                    % (MAX_UNCOMPRESSED_BYTES // (1024 * 1024))
                )

            parts: Dict[str, bytes] = {}
            for info in infos:
                name = normalize_part_name(info.filename)
                if name in parts:
                    raise GuardError("DOCX contains a duplicate package part: %s" % name)
                parts[name] = archive.read(info)
            return parts
    except zipfile.BadZipFile as exc:
        raise GuardError("Invalid DOCX/ZIP package: %s" % exc) from exc


def local_name(expanded_name: str) -> str:
    if "}" in expanded_name:
        return expanded_name.rsplit("}", 1)[1]
    return expanded_name


def canonical_attributes(attributes: Dict[str, str]) -> List[List[str]]:
    filtered = [
        [name, value]
        for name, value in attributes.items()
        if local_name(name) not in VOLATILE_ATTRIBUTE_LOCALS
    ]
    filtered.sort(key=lambda item: (item[0], item[1]))
    return filtered


def canonical_element(element: ET.Element, include_children: bool) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "tag": element.tag,
        "attributes": canonical_attributes(element.attrib),
    }
    if include_children:
        text = (element.text or "").strip()
        if text:
            result["text"] = text
        result["children"] = [
            canonical_element(child, True) for child in list(element)
        ]
    return result


def element_fingerprint(element: ET.Element, mode: str) -> str:
    payload = canonical_element(element, include_children=(mode == "subtree"))
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256_bytes(encoded)


def extract_format_sequences(parts: Dict[str, bytes]) -> Dict[str, Dict[str, List[str]]]:
    package_sequences: Dict[str, Dict[str, List[str]]] = {}

    for part_name in sorted(parts):
        if not part_name.lower().endswith(".xml"):
            continue
        try:
            root = ET.fromstring(parts[part_name])
        except ET.ParseError as exc:
            raise GuardError("Cannot parse XML part %s: %s" % (part_name, exc)) from exc

        sequences: Dict[str, List[str]] = {}
        for element in root.iter():
            rule = FORMAT_RULES.get(element.tag)
            if rule:
                category, mode, _strict = rule
                sequences.setdefault(category, []).append(
                    element_fingerprint(element, mode)
                )
            if element.tag == W_BR and element.attrib.get(W_TYPE) == "page":
                sequences.setdefault("explicit_page_break", []).append(
                    element_fingerprint(element, "attributes")
                )

        if sequences:
            package_sequences[part_name] = sequences

    return package_sequences


def strict_categories() -> set:
    categories = {
        category
        for category, _mode, strict in FORMAT_RULES.values()
        if strict
    }
    categories.add("explicit_page_break")
    return categories


def create_baseline(source: Path) -> Dict[str, Any]:
    parts = load_package(source)
    part_hashes = {name: sha256_bytes(data) for name, data in sorted(parts.items())}
    protected = {
        name: part_hashes[name]
        for name in sorted(part_hashes)
        if is_protected_part(name)
    }
    format_sequences = extract_format_sequences(parts)
    format_node_count = sum(
        len(sequence)
        for categories in format_sequences.values()
        for sequence in categories.values()
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "path": str(source.resolve()),
            "sha256": file_sha256(source),
            "size": source.stat().st_size,
        },
        "package_parts": part_hashes,
        "protected_parts": protected,
        "format_sequences": format_sequences,
        "summary": {
            "package_part_count": len(part_hashes),
            "protected_part_count": len(protected),
            "format_node_count": format_node_count,
        },
    }


def match_ordered_subsequence(
    expected: List[str], actual: List[str]
) -> Tuple[bool, List[str]]:
    expected_index = 0
    additions: List[str] = []
    for fingerprint in actual:
        if expected_index < len(expected) and fingerprint == expected[expected_index]:
            expected_index += 1
        else:
            additions.append(fingerprint)
    return expected_index == len(expected), additions


def verify_baseline(
    baseline: Dict[str, Any],
    output_path: Path,
    original_path: Optional[Path],
    allowed_removed_parts: Iterable[str],
) -> Dict[str, Any]:
    if baseline.get("schema_version") != SCHEMA_VERSION:
        raise GuardError(
            "Unsupported baseline schema version: %r"
            % baseline.get("schema_version")
        )

    baseline_parts = baseline.get("package_parts")
    baseline_protected = baseline.get("protected_parts")
    baseline_sequences = baseline.get("format_sequences")
    source = baseline.get("source")
    if not isinstance(baseline_parts, dict) or not isinstance(baseline_protected, dict):
        raise GuardError("Baseline is missing package-part hashes")
    if not isinstance(baseline_sequences, dict) or not isinstance(source, dict):
        raise GuardError("Baseline is missing format sequences or source metadata")

    output_parts = load_package(output_path)
    output_hashes = {
        name: sha256_bytes(data) for name, data in sorted(output_parts.items())
    }
    output_sequences = extract_format_sequences(output_parts)

    baseline_names = set(baseline_parts)
    output_names = set(output_hashes)
    added_parts = sorted(output_names - baseline_names)
    removed_parts = sorted(baseline_names - output_names)
    modified_parts = sorted(
        name
        for name in baseline_names & output_names
        if baseline_parts[name] != output_hashes[name]
    )
    unchanged_count = len(baseline_names & output_names) - len(modified_parts)

    errors: List[Dict[str, Any]] = []
    warnings: List[str] = []

    original_check: Optional[Dict[str, Any]] = None
    if original_path:
        actual_original_hash = file_sha256(original_path)
        original_check = {
            "path": str(original_path.resolve()),
            "expected_sha256": source.get("sha256"),
            "actual_sha256": actual_original_hash,
            "unchanged": actual_original_hash == source.get("sha256"),
        }
        if not original_check["unchanged"]:
            errors.append(
                {
                    "check": "original_file",
                    "message": "The original DOCX no longer matches the baseline hash",
                }
            )
    else:
        warnings.append(
            "Original-file integrity was not checked; pass --original to verify it was not overwritten"
        )

    output_protected_names = {
        name for name in output_names if is_protected_part(name)
    }
    baseline_protected_names = set(baseline_protected)
    protected_added = sorted(output_protected_names - baseline_protected_names)
    protected_removed = sorted(baseline_protected_names - output_protected_names)
    protected_modified = sorted(
        name
        for name in baseline_protected_names & output_protected_names
        if baseline_protected[name] != output_hashes[name]
    )
    if protected_added or protected_removed or protected_modified:
        errors.append(
            {
                "check": "protected_parts",
                "message": "Protected DOCX package parts changed",
                "added": protected_added,
                "removed": protected_removed,
                "modified": protected_modified,
            }
        )

    allowed_removed = {normalize_part_name(name) for name in allowed_removed_parts}
    unapproved_removed = sorted(set(removed_parts) - allowed_removed)
    if unapproved_removed:
        errors.append(
            {
                "check": "removed_parts",
                "message": "Original package parts were removed without approval",
                "parts": unapproved_removed,
            }
        )

    strict = strict_categories()
    format_failures: List[Dict[str, Any]] = []
    format_additions: List[Dict[str, Any]] = []
    sequence_parts = sorted(set(baseline_sequences) | set(output_sequences))
    for part_name in sequence_parts:
        baseline_categories = baseline_sequences.get(part_name, {})
        output_categories = output_sequences.get(part_name, {})
        category_names = sorted(set(baseline_categories) | set(output_categories))
        for category in category_names:
            expected = baseline_categories.get(category)
            actual = output_categories.get(category, [])
            if expected is None:
                format_failures.append(
                    {
                        "part": part_name,
                        "category": category,
                        "expected_count": 0,
                        "actual_count": len(actual),
                        "comparison": "local-format-donor",
                        "reason": "New formatting category has no donor in the original part",
                    }
                )
                continue

            if category in strict:
                passed = expected == actual
                additions: List[str] = []
            else:
                passed, additions = match_ordered_subsequence(expected, actual)

            if not passed:
                format_failures.append(
                    {
                        "part": part_name,
                        "category": category,
                        "expected_count": len(expected),
                        "actual_count": len(actual),
                        "comparison": "exact" if category in strict else "ordered-subsequence",
                        "reason": "Existing formatting sequence changed, disappeared, or reordered",
                    }
                )
                continue

            if additions:
                donor_fingerprints = set(expected)
                unknown_additions = sorted(set(additions) - donor_fingerprints)
                if unknown_additions:
                    format_failures.append(
                        {
                            "part": part_name,
                            "category": category,
                            "expected_count": len(expected),
                            "actual_count": len(actual),
                            "comparison": "local-format-donor",
                            "reason": "Added formatting nodes do not clone an original local format",
                            "unknown_fingerprint_count": len(unknown_additions),
                        }
                    )
                else:
                    format_additions.append(
                        {
                            "part": part_name,
                            "category": category,
                            "added_count": len(additions),
                            "donor_verified": True,
                        }
                    )

    if format_failures:
        errors.append(
            {
                "check": "format_sequences",
                "message": "Existing formatting nodes changed, disappeared, reordered, or introduced without a local donor",
                "failures": format_failures,
            }
        )

    result = {
        "status": "ok" if not errors else "error",
        "baseline_source": source,
        "output": {
            "path": str(output_path.resolve()),
            "sha256": file_sha256(output_path),
            "size": output_path.stat().st_size,
        },
        "original_check": original_check,
        "protected_parts": {
            "passed": not (protected_added or protected_removed or protected_modified),
            "added": protected_added,
            "removed": protected_removed,
            "modified": protected_modified,
        },
        "format_check": {
            "passed": not format_failures,
            "failures": format_failures,
            "allowed_additions": format_additions,
        },
        "package_changes": {
            "added": added_parts,
            "removed": removed_parts,
            "modified": modified_parts,
            "unchanged_count": unchanged_count,
        },
        "errors": errors,
        "warnings": warnings,
    }
    return result


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def print_snapshot_result(baseline: Dict[str, Any], output_path: Path, json_output: bool) -> None:
    if json_output:
        print(
            json.dumps(
                {
                    "status": "ok",
                    "baseline": str(output_path.resolve()),
                    "summary": baseline["summary"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    print("Format baseline created: %s" % output_path.resolve())
    print("  package parts: %d" % baseline["summary"]["package_part_count"])
    print("  protected parts: %d" % baseline["summary"]["protected_part_count"])
    print("  formatting nodes: %d" % baseline["summary"]["format_node_count"])


def print_verify_result(result: Dict[str, Any], json_output: bool) -> None:
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    label = "PASS" if result["status"] == "ok" else "FAIL"
    print("DOCX format verification: %s" % label)
    print("  output: %s" % result["output"]["path"])
    print("  protected parts: %s" % ("unchanged" if result["protected_parts"]["passed"] else "changed"))
    print("  formatting nodes: %s" % ("preserved" if result["format_check"]["passed"] else "changed"))
    print("  modified package parts: %d" % len(result["package_changes"]["modified"]))
    print("  added package parts: %d" % len(result["package_changes"]["added"]))
    print("  removed package parts: %d" % len(result["package_changes"]["removed"]))
    for warning in result["warnings"]:
        print("  warning: %s" % warning)
    for error in result["errors"]:
        print("  error: %s" % error["message"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create and verify immutable-format baselines for existing DOCX templates"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser(
        "snapshot", help="Record protected package hashes and formatting fingerprints"
    )
    snapshot_parser.add_argument("docx", help="Original DOCX template")
    snapshot_parser.add_argument("-o", "--output", required=True, help="Baseline JSON path")
    snapshot_parser.add_argument("--json", action="store_true", dest="json_output")

    verify_parser = subparsers.add_parser(
        "verify", help="Compare an edited DOCX against a saved baseline"
    )
    verify_parser.add_argument("baseline", help="Baseline JSON path")
    verify_parser.add_argument("docx", help="Edited DOCX output")
    verify_parser.add_argument(
        "--original",
        help="Original DOCX path; verifies that the source file was not overwritten",
    )
    verify_parser.add_argument(
        "--manifest",
        help="Write the complete verification manifest to this JSON path",
    )
    verify_parser.add_argument(
        "--allow-removed-part",
        action="append",
        default=[],
        help="Allow one explicitly targeted non-protected package part to be removed",
    )
    verify_parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "snapshot":
            source = Path(args.docx)
            output = Path(args.output)
            baseline = create_baseline(source)
            write_json(output, baseline)
            print_snapshot_result(baseline, output, args.json_output)
            return 0

        baseline_path = Path(args.baseline)
        if not baseline_path.is_file():
            raise GuardError("Baseline file does not exist: %s" % baseline_path)
        try:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GuardError("Cannot read baseline JSON: %s" % exc) from exc

        result = verify_baseline(
            baseline=baseline,
            output_path=Path(args.docx),
            original_path=Path(args.original) if args.original else None,
            allowed_removed_parts=args.allow_removed_part,
        )
        if args.manifest:
            write_json(Path(args.manifest), result)
        print_verify_result(result, args.json_output)
        return 0 if result["status"] == "ok" else 1
    except (GuardError, OSError) as exc:
        payload = {"status": "error", "error": str(exc)}
        if getattr(args, "json_output", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("Error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())