from pkg_resources import get_distribution, DistributionNotFound
from subprocess import call
from shutil import which
from unittest import main, skipUnless, TestCase

mypy_version = 0.0
try:
    mypy_version = float(get_distribution("mypy").version)
except DistributionNotFound:
    pass


class TypeCheck(TestCase):
    @skipUnless(mypy_version >= 0.942, "Do not trust earlier mypy versions")
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


if __name__ == "__main__":
    main()
