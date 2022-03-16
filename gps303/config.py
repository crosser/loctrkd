from configparser import ConfigParser

PORT = 4303
DBFN = "/var/lib/gps303/gps303.sqlite"

def readconfig(fname):
    config = ConfigParser()
    config["daemon"] = {
        "port": PORT,
        "dbfn": DBFN,
    }
    config["device"] = {}
    #_print_config(config)
    #print("now reading", fname)
    config.read(fname)
    #_print_config(config)
    return config

def _print_config(conf):
    for section in conf.sections():
        print("section", section)
        for option in conf.options(section):
            print("    ", option, conf[section][option])

if __name__ == "__main__":
    from sys import argv
    conf = readconfig(argv[1])
    _print_config(conf)
    print("binaryswitch", int(conf.get("device", "binaryswitch"), 0))
