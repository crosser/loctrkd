from getopt import getopt
from logging import getLogger, StreamHandler, DEBUG, INFO
from logging.handlers import SysLogHandler
from select import poll, POLLIN, POLLERR, POLLHUP, POLLPRI
from socket import socket, AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
import sys
from time import time

from .config import readconfig
from .gps303proto import handle_packet, make_response, LOGIN, set_config
from .evstore import initdb, stow
from .lookaside import prepare_response

CONF = "/etc/gps303.conf"

log = getLogger("gps303")

if __name__.endswith("__main__"):
    opts, _ = getopt(sys.argv[1:], "c:d")
    opts = dict(opts)
    conf = readconfig(opts["-c"] if "-c" in opts else CONF)

    if sys.stdout.isatty():
        log.addHandler(StreamHandler(sys.stderr))
    else:
        log.addHandler(SysLogHandler(address="/dev/log"))
    log.setLevel(DEBUG if "-d" in opts else INFO)
    log.info("starting with options: %s", opts)

    initdb(conf.get("storage", "dbfn"))
    set_config(conf)

    ctlsock = socket(AF_INET, SOCK_STREAM)
    ctlsock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    ctlsock.bind(("", conf.getint("collector", "port")))
    ctlsock.listen(5)
    ctlfd = ctlsock.fileno()
    pollset = poll()
    pollset.register(ctlfd, POLLIN | POLLERR | POLLHUP | POLLPRI)
    clnt_dict = {}
    while True:
        try:
            events = pollset.poll(1000)
        except KeyboardInterrupt:
            log.info("Exiting")
            sys.exit(0)
        for fd, ev in events:
            if fd == ctlfd:
                if ev & POLLIN:
                    clntsock, clntaddr = ctlsock.accept()
                    clntfd = clntsock.fileno()
                    clnt_dict[clntfd] = (clntsock, clntaddr, None)
                    pollset.register(
                        clntfd, POLLIN | POLLERR | POLLHUP | POLLPRI
                    )
                    log.debug(
                        "accepted connection from %s as fd %d",
                        clntaddr,
                        clntfd,
                    )
                if ev & ~POLLIN:
                    log.debug("unexpected event on ctlfd: %s", ev)
            else:
                try:
                    clntsock, clntaddr, imei = clnt_dict[fd]
                except KeyError:  # this socket closed already
                    continue
                if ev & POLLIN:
                    packet = clntsock.recv(4096)
                    when = time()
                    if packet:
                        msg = handle_packet(packet)
                        log.debug("%s from %s fd %d", msg, clntaddr, fd)
                        if isinstance(msg, LOGIN):
                            imei = msg.imei
                            clnt_dict[fd] = (clntsock, clntaddr, imei)
                        stow(
                            clntaddr,
                            when,
                            imei,
                            msg.length,
                            msg.PROTO,
                            msg.payload,
                        )
                        kwargs = prepare_response(conf, msg)
                        response = make_response(msg, **kwargs)
                        if response:
                            try:
                                # Ignore possibility of blocking
                                clntsock.send(make_response(msg))
                            except OSError as e:
                                log.debug("sending to fd %d error %s", fd, e)
                    else:
                        # TODO: Also disconnect on HIBERNATION
                        log.info("disconnect fd %d imei %s", fd, imei)
                        pollset.unregister(fd)
                        clntsock.close()
                        del clnt_dict[fd]
                if ev & ~POLLIN:
                    log.warning("unexpected event", ev, "on fd", fd)
