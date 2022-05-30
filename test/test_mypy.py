from subprocess import run
from shutil import which
from unittest import TestCase


class TypeCheck(TestCase):
    def test_mypy(self):
        if not which("mypy"):
            self.fail(f"mypy not installed.")
        cmd = ["mypy", "--strict", "--ignore-missing-imports", "gps303"]
        output = run(cmd, capture_output=True)
        if output.returncode != 0:
            self.fail(
                f"mypy exited with code {output.returncode}:\n{output.stderr.decode()}"
            )
