from setuptools import setup
from re import findall

with open("debian/changelog", "r") as clog:
    _, version, _ = findall(
        r"(?P<src>.*) \((?P<version>.*)\) (?P<suite>.*); .*",
        clog.readline().strip(),
    )[0]

setup(
    name="loctrkd",
    version=version,
    description="Suite of daemons to collect reports from xz303 GPS trackers",
    url="http://www.average.org/loctrkd/",
    author="Eugene Crosser",
    author_email="crosser@average.org",
    install_requires=["zeromq"],
    license="MIT",
    packages=[
        "loctrkd",
    ],
    scripts=["scripts/loctrkd"],
    long_description=open("README.md").read(),
)
