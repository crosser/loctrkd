from configparser import ConfigParser

PORT = 4303
DBFN = "/var/lib/gps303/gps303.sqlite"

def readconfig(fname):
    config = ConfigParser()
    config.read(fname)
    if not config.has_section("daemon"):
        config.add_section("daemon")
    if not config.has_option("daemon", "port"):
        config["daemon"]["port"] = str(PORT)
    if not config.has_option("daemon", "dbfn"):
        config["daemon"]["dbfn"] = DBFN
    return config

if __name__ == "__main__":
    from sys import argv
    conf = readconfig(argv[1])
    for section in conf.sections():
        print("section", section)
        for option in conf.options(section):
            print("    ", option, conf[section][option])
    print("binaryswitch", int(conf.get("device", "binaryswitch"), 0))
