from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    value: str
    kind: str
    line: int
    column: int
    start: int
    end: int


OPERATORS = ("[[", "]]", "&&", "||", ";;", ";&", ";;&", "<<-", "<<<", ">>", "<<", "==", "!=", "=~", ">=", "<=", "&>", ">&", "|&")
TEST_OPERATORS = ("-eq", "-ne", "-gt", "-ge", "-lt", "-le")


def tokenize(text: str) -> list[Token]:
    out: list[Token] = []
    index = 0
    line = 1
    column = 1
    at_word_start = True

    def advance(fragment: str) -> None:
        nonlocal line, column, at_word_start
        if "\n" in fragment:
            line += fragment.count("\n")
            column = len(fragment.rsplit("\n", 1)[-1]) + 1
            at_word_start = True
        else:
            column += len(fragment)

    while index < len(text):
        start = index
        start_line = line
        start_column = column
        character = text[index]
        if character.isspace():
            index += 1
            while index < len(text) and text[index].isspace():
                index += 1
            advance(text[start:index])
            continue
        if character == "#" and (at_word_start or index == 0):
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
            advance(text[start:index])
            continue
        if character in {"'", '"', '`'}:
            quote = character
            index += 1
            escaped = False
            while index < len(text):
                current = text[index]
                index += 1
                if quote == "'":
                    if current == quote:
                        break
                elif escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == quote:
                    break
            fragment = text[start:index]
            out.append(Token(fragment, "string", start_line, start_column, start, index))
            advance(fragment)
            at_word_start = False
            continue
        test_operator = next((value for value in TEST_OPERATORS if text.startswith(value, index) and (index + len(value) == len(text) or not text[index + len(value)].isalnum())), None)
        operator = test_operator or next((value for value in OPERATORS if text.startswith(value, index)), None)
        if operator:
            index += len(operator)
            out.append(Token(operator, "operator", start_line, start_column, start, index))
            advance(operator)
            at_word_start = operator in {";", ";;", "&&", "||", "|"}
            continue
        if character.isalpha() or character == "_":
            index += 1
            while index < len(text) and (text[index].isalnum() or text[index] == "_"):
                index += 1
            fragment = text[start:index]
            out.append(Token(fragment, "identifier", start_line, start_column, start, index))
            advance(fragment)
            at_word_start = False
            continue
        if character.isdigit():
            index += 1
            while index < len(text) and text[index].isdigit():
                index += 1
            fragment = text[start:index]
            out.append(Token(fragment, "number", start_line, start_column, start, index))
            advance(fragment)
            at_word_start = False
            continue
        index += 1
        out.append(Token(character, "operator", start_line, start_column, start, index))
        advance(character)
        at_word_start = character in {";", "|", "&", "("}
    return out


import os
from pathlib import Path
from typing import Sequence

EXCLUDED_DIRS = {".git", ".hg", ".bats", "coverage", "node_modules", "target", "vendor"}


def discover_files(root: Path, filters: Sequence[str] = ()) -> list[Path]:
    files: list[Path] = []
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in EXCLUDED_DIRS and name not in {"test", "tests"})
        for filename in sorted(filenames):
            path = Path(directory, filename)
            if path.suffix not in {".sh", ".bash"}:
                try:
                    first = path.open(encoding="utf-8", errors="ignore").readline()
                except OSError:
                    continue
                if "bash" not in first and "sh" not in first:
                    continue
            relative = path.relative_to(root).as_posix()
            if filters and not any(fragment in relative for fragment in filters):
                continue
            files.append(path)
    return files


import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Function:
    name: str
    file: str
    start_line: int
    end_line: int
    complexity: int


@dataclass(frozen=True)
class Metric:
    name: str
    file: str
    start_line: int
    end_line: int
    complexity: int
    coverage: float | None
    crap: float | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def score(complexity: int, coverage_percent: float | None) -> float | None:
    if coverage_percent is None:
        return None
    uncovered = 1 - coverage_percent / 100
    return complexity * complexity * uncovered**3 + complexity


def _matching_brace(tokens: list[Token], open_index: int) -> int | None:
    depth = 0
    for index in range(open_index, len(tokens)):
        if tokens[index].value == "{":
            depth += 1
        elif tokens[index].value == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _complexity(tokens: list[Token]) -> int:
    value = 1
    for token in tokens:
        if token.value in {"if", "elif", "for", "while", "until", "select", "case"} or token.value in {"&&", "||"}:
            value += 1
    return value


def extract_functions(path: Path, root: Path) -> list[Function]:
    text = path.read_text(encoding="utf-8")
    tokens = tokenize(text)
    out: list[Function] = []
    pattern = re.compile(r"(?m)^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\s*\))?\s*\{")
    for match in pattern.finditer(text):
        open_index = next((index for index, token in enumerate(tokens) if token.start >= match.start() and token.value == "{"), None)
        if open_index is None:
            continue
        close_index = _matching_brace(tokens, open_index)
        if close_index is None:
            continue
        out.append(Function(match.group(1), path.relative_to(root).as_posix(), tokens[open_index].line, tokens[close_index].line, _complexity(tokens[open_index + 1:close_index])))
    if not out and tokens:
        out.append(Function("<script>", path.relative_to(root).as_posix(), 1, tokens[-1].line, _complexity(tokens)))
    return out


def load_coverage(path: Path) -> dict[str, list[tuple[int, int]]]:
    if path.is_dir():
        candidates = sorted(path.rglob("cobertura.xml")) + sorted(path.rglob("lcov.info"))
        if not candidates:
            raise FileNotFoundError(f"no cobertura.xml or lcov.info under {path}")
        path = candidates[0]
    if path.suffix == ".xml":
        result: dict[str, list[tuple[int, int]]] = {}
        root = ET.fromstring(path.read_text(encoding="utf-8"))
        for class_node in root.findall(".//class"):
            filename = class_node.attrib.get("filename", "").replace("\\", "/").removeprefix("./")
            result.setdefault(filename, [])
            for line in class_node.findall("./lines/line"):
                result[filename].append((int(line.attrib["number"]), int(float(line.attrib.get("hits", "0")))))
        return result
    result: dict[str, list[tuple[int, int]]] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("SF:"):
            current = raw[3:].replace("\\", "/").removeprefix("./")
            result.setdefault(current, [])
        elif raw.startswith("DA:") and current:
            line, count, *_ = raw[3:].split(",")
            result[current].append((int(line), int(count)))
    return result


def _points(coverage: dict[str, list[tuple[int, int]]], filename: str) -> list[tuple[int, int]] | None:
    if filename in coverage:
        return coverage[filename]
    matches = [value for key, value in coverage.items() if key.endswith("/" + filename) or filename.endswith("/" + key)]
    return matches[0] if len(matches) == 1 else None


def analyze(root: Path, coverage_path: Path | None, filters: Sequence[str] = ()) -> list[Metric]:
    coverage = load_coverage(coverage_path) if coverage_path and coverage_path.exists() else {}
    metrics: list[Metric] = []
    for path in discover_files(root, filters):
        for function in extract_functions(path, root):
            points = _points(coverage, function.file)
            percent: float | None = None
            if points is not None:
                relevant = [(line, hits) for line, hits in points if function.start_line <= line <= function.end_line]
                percent = 0.0 if not relevant else 100 * sum(hits > 0 for _, hits in relevant) / len(relevant)
            metrics.append(Metric(**asdict(function), coverage=percent, crap=score(function.complexity, percent)))
    metrics.sort(key=lambda item: (item.crap is None, -(item.crap or 0), item.name))
    return metrics


def run_test_command(command: str, root: Path) -> None:
    completed = subprocess.run(command, cwd=root, shell=True, check=False)
    if completed.returncode:
        raise RuntimeError(f"test command failed with status {completed.returncode}")


def format_report(metrics: list[Metric]) -> str:
    header = f"{'Function':30} {'File':44} {'CC':>4} {'Cov%':>7} {'CRAP':>8}"
    lines = ["CRAP Report", "===========", header, "-" * len(header)]
    for metric in metrics:
        coverage = "N/A" if metric.coverage is None else f"{metric.coverage:.1f}%"
        crap = "N/A" if metric.crap is None else f"{metric.crap:.1f}"
        lines.append(f"{metric.name[:30]:30} {metric.file[:44]:44} {metric.complexity:4d} {coverage:>7} {crap:>8}")
    return "\n".join(lines) + "\n"
