from subprocess import call
from shutil import which
from unittest import TestCase


class TypeCheck(TestCase):
    def test_mypy(self) -> None:
        if not which("mypy"):
            self.fail("mypy not installed.")
        cmd = [
            "mypy",
            "--strict",
            "--ignore-missing-imports",
            "gps303",
            "test",
        ]
        self.assertEqual(call(cmd), 0, "mypy typecheck")
