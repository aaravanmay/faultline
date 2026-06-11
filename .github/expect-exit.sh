#!/usr/bin/env bash
# Run a command and assert it exits with a specific code.
# Usage: expect-exit.sh <expected-code> <command...>
set -u
expected="$1"; shift
"$@"
actual=$?
if [ "$actual" -ne "$expected" ]; then
  echo "expect-exit: expected exit $expected, got $actual" >&2
  exit 1
fi
echo "expect-exit: got expected exit $expected"
