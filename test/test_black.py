from glob import glob
from subprocess import run
from shutil import which
from unittest import TestCase


class BlackFormatter(TestCase):
    def test_black(self):
        if not which("black"):
            self.fail(f"black not installed.")
        cmd = (
            ["black", "--check", "--diff", "-l", "79"]
            + glob("gps303/**/*.py", recursive=True)
            + glob("test/**/*.py", recursive=True)
        )
        output = run(cmd, capture_output=True)
        if output.returncode == 1:
            self.fail(
                f"black found code that needs reformatting:\n{output.stdout.decode()}"
            )
        if output.returncode != 0:
            self.fail(
                f"black exited with code {output.returncode}:\n{output.stderr.decode()}"
            )
