""" Common housekeeping for all daemons """

from configparser import ConfigParser, SectionProxy
from getopt import getopt
from logging import Formatter, getLogger, Logger, StreamHandler, DEBUG, INFO
from logging.handlers import SysLogHandler
from pkg_resources import get_distribution, DistributionNotFound
from sys import argv, stderr, stdout
from typing import Any, Dict, List, Optional, Tuple, Union

CONF = "/etc/gps303.conf"
PORT = 4303
DBFN = "/var/lib/gps303/gps303.sqlite"

try:
    version = get_distribution("gps303").version
except DistributionNotFound:
    version = "<local>"


def init(
    log: Logger, opts: Optional[List[Tuple[str, str]]] = None
) -> ConfigParser:
    if opts is None:
        opts, _ = getopt(argv[1:], "c:d")
    dopts = dict(opts)
    conf = readconfig(dopts["-c"] if "-c" in dopts else CONF)
    log.setLevel(DEBUG if "-d" in dopts else INFO)
    if stdout.isatty():
        fhdl = StreamHandler(stderr)
        fhdl.setFormatter(
            Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        log.addHandler(fhdl)
        log.debug("%s starting with options: %s", version, dopts)
    else:
        lhdl = SysLogHandler(address="/dev/log")
        lhdl.setFormatter(
            Formatter("%(name)s[%(process)d]: %(levelname)s - %(message)s")
        )
        log.addHandler(lhdl)
        log.info("%s starting with options: %s", version, dopts)
    return conf


def readconfig(fname: str) -> ConfigParser:
    config = ConfigParser()
    config["collector"] = {
        "port": str(PORT),
    }
    config["storage"] = {
        "dbfn": DBFN,
    }
    config["termconfig"] = {}
    config.read(fname)
    return config


def normconf(section: SectionProxy) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, val in section.items():
        vals = val.split("\n")
        if len(vals) > 1 and vals[0] == "":
            vals = vals[1:]
        lst: List[Union[str, int]] = []
        for el in vals:
            try:
                lst.append(int(el, 0))
            except ValueError:
                if el[0] == '"' and el[-1] == '"':
                    el = el.strip('"').rstrip('"')
                lst.append(el)
        if not (
            all([isinstance(x, int) for x in lst])
            or all([isinstance(x, str) for x in lst])
        ):
            raise ValueError(
                "Values of %s - %s are of different type", key, vals
            )
        if len(lst) == 1:
            result[key] = lst[0]
        else:
            result[key] = lst
    return result


if __name__ == "__main__":
    from sys import argv

    def _print_config(conf: ConfigParser) -> None:
        for section in conf.sections():
            print("section", section)
            for option in conf.options(section):
                print("    ", option, conf[section][option])

    conf = readconfig(argv[1])
    _print_config(conf)
    print(normconf(conf["termconfig"]))
