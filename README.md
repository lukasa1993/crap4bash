# crap4bash

`crap4bash` calculates CRAP scores for Bash functions. It uses a shell-aware lexer and reads kcov Cobertura XML or LCOV coverage.

## Install

```bash
pipx install git+https://github.com/lukasa1993/crap4bash.git
```

## Run

```bash
crap4bash --test-command "kcov target/coverage bats tests" --coverage target/coverage --fail-over 6
```

The coverage path can be a report file or a directory. The tool searches a directory for `cobertura.xml` or `lcov.info`.

Use `--no-test` for an existing report and `--json` for machine-readable output.
