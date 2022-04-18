""" Common housekeeping for all daemons """

from configparser import ConfigParser
from getopt import getopt
from logging import getLogger, StreamHandler, DEBUG, INFO
from sys import argv, stderr, stdout

CONF = "/etc/gps303.conf"
PORT = 4303
DBFN = "/var/lib/gps303/gps303.sqlite"

def init(log):
    opts, _ = getopt(argv[1:], "c:d")
    opts = dict(opts)
    conf = readconfig(opts["-c"] if "-c" in opts else CONF)
    if stdout.isatty():
        log.addHandler(StreamHandler(stderr))
    else:
        log.addHandler(SysLogHandler(address="/dev/log"))
    log.setLevel(DEBUG if "-d" in opts else INFO)
    log.info("starting with options: %s", opts)
    return conf

def readconfig(fname):
    config = ConfigParser()
    config["collector"] = {
        "port": PORT,
    }
    config["storage"] = {
        "dbfn": DBFN,
    }
    config["device"] = {}
    #_print_config(config)
    #print("now reading", fname)
    config.read(fname)
    #_print_config(config)
    return config

if __name__ == "__main__":
    from sys import argv

    def _print_config(conf):
        for section in conf.sections():
            print("section", section)
            for option in conf.options(section):
                print("    ", option, conf[section][option])

    conf = readconfig(argv[1])
    _print_config(conf)
    print("binaryswitch", int(conf.get("device", "binaryswitch"), 0))
