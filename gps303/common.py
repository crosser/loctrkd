""" Common housekeeping for all daemons """

from configparser import ConfigParser
from getopt import getopt
from logging import Formatter, getLogger, StreamHandler, DEBUG, INFO
from logging.handlers import SysLogHandler
from pkg_resources import get_distribution, DistributionNotFound
from sys import argv, stderr, stdout

CONF = "/etc/gps303.conf"
PORT = 4303
DBFN = "/var/lib/gps303/gps303.sqlite"

try:
    version = get_distribution("gps303").version
except DistributionNotFound:
    version = "<local>"


def init(log, opts=None):
    if opts is None:
        opts, _ = getopt(argv[1:], "c:d")
    opts = dict(opts)
    conf = readconfig(opts["-c"] if "-c" in opts else CONF)
    if stdout.isatty():
        hdl = StreamHandler(stderr)
        hdl.setFormatter(
            Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        log.addHandler(hdl)
    else:
        hdl = SysLogHandler(address="/dev/log")
        hdl.setFormatter(
            Formatter("%(name)s[%(process)d]: %(levelname)s - %(message)s")
        )
        log.addHandler(hdl)
    log.setLevel(DEBUG if "-d" in opts else INFO)
    log.info("%s starting with options: %s", version, opts)
    return conf


def readconfig(fname):
    config = ConfigParser()
    config["collector"] = {
        "port": PORT,
    }
    config["storage"] = {
        "dbfn": DBFN,
    }
    config["termconfig"] = {}
    config.read(fname)
    return config


def normconf(section):
    result = {}
    for key, val in section.items():
        vals = val.split("\n")
        if len(vals) > 1 and vals[0] == "":
            vals = vals[1:]
        lst = []
        for el in vals:
            try:
                el = int(el, 0)
            except ValueError:
                if el[0] == '"' and el[-1] == '"':
                    el = el.strip('"').rstrip('"')
            lst.append(el)
        if len(lst) == 1:
            [lst] = lst
        result[key] = lst
    return result


if __name__ == "__main__":
    from sys import argv

    def _print_config(conf):
        for section in conf.sections():
            print("section", section)
            for option in conf.options(section):
                print("    ", option, conf[section][option])

    conf = readconfig(argv[1])
    _print_config(conf)
    print(normconf(conf["termconfig"]))
