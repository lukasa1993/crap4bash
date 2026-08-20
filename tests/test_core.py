from pathlib import Path

from crap4bash.core import analyze, extract_functions, score


def test_extracts_function_complexity(tmp_path: Path) -> None:
    source = tmp_path / "sample.sh"
    source.write_text("""#!/usr/bin/env bash
choose() {
  if [[ $1 == yes ]] && true; then
    echo yes
  fi
}
""", encoding="utf-8")
    function = extract_functions(source, tmp_path)[0]
    assert function.name == "choose"
    assert function.complexity == 3


def test_maps_cobertura(tmp_path: Path) -> None:
    source = tmp_path / "sample.sh"
    source.write_text("f() {\n echo a\n echo b\n}\n", encoding="utf-8")
    report = tmp_path / "cobertura.xml"
    report.write_text('<coverage><packages><package><classes><class filename="sample.sh"><lines><line number="2" hits="1"/><line number="3" hits="0"/></lines></class></classes></package></packages></coverage>', encoding="utf-8")
    metric = analyze(tmp_path, report)[0]
    assert metric.coverage == 50
    assert metric.crap == score(1, 50)
