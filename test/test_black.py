from glob import glob
from pkg_resources import get_distribution, DistributionNotFound
from re import match
from subprocess import run
from shutil import which
from unittest import main, TestCase, skipUnless

black_version = 0.0
try:
    vermatch = match("[\.\d]*", get_distribution("black").version)
    if vermatch is not None:
        black_version = float(vermatch.group())
except DistributionNotFound:
    pass


class BlackFormatter(TestCase):
    @skipUnless(black_version >= 21.1, "Do not trust earlier black versions")
    def test_black(self) -> None:
        if not which("black"):
            self.fail(f"black not installed.")
        cmd = (
            ["black", "--check", "--diff", "-l", "79"]
            + glob("loctrkd/**/*.py", recursive=True)
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


if __name__ == "__main__":
    main()
