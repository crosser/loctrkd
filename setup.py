from setuptools import setup
from re import findall

with open("debian/changelog", "r") as clog:
    _, version, _ = findall(
        r"(?P<src>.*) \((?P<version>.*)\) (?P<suite>.*); .*",
        clog.readline().strip(),
    )[0]

setup(
    name="gps303",
    version=version,
    description="Suite of daemons to collect reports from xz303 GPS trackers",
    url="http://www.average.org/gps303/",
    author="Eugene Crosser",
    author_email="crosser@average.org",
    install_requires=["zeromq"],
    license="MIT",
    packages=[
        "gps303",
    ],
    scripts=["scripts/gps303"],
    long_description=open("README.md").read(),
)
