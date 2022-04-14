from getopt import getopt
from logging import getLogger, StreamHandler, DEBUG, INFO
from logging.handlers import SysLogHandler
from socket import socket, AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
from time import time
import sys
import zmq

from .config import readconfig
from .GT06mod import handle_packet, make_response, LOGIN, set_config

CONF = "/etc/gps303.conf"

log = getLogger("gps303/collector")


class Bcast:
    def __init__(self, imei, msg):
        self.as_bytes = imei.encode() + msg.encode()


class Zmsg:
    def __init__(self, msg):
        self.imei = msg[:16].decode()
        self.payload = msg[16:]


class Client:
    def __init__(self, clntsock, clntaddr):
        self.clntsock = clntsock
        self.clntaddr = clntaddr
        self.buffer = b""
        self.imei = None

    def close(self):
        self.clntsock.close()

    def recv(self):
        packet = self.clntsock.recv(4096)
        if not packet:
            return None
        when = time()
        self.buffer += packet
        # implement framing properly
        msg = handle_packet(packet, self.clntaddr, when)
        self.buffer = self.buffer[len(packet):]
        if isinstance(msg, LOGIN):
            self.imei = msg.imei
        return msg

    def send(self, buffer):
        self.clntsock.send(buffer)


class Clients:
    def __init__(self):
        self.by_fd = {}
        self.by_imei = {}

    def add(self, clntsock, clntaddr):
        fd = clntsock.fileno()
        self.by_fd[fd] = Client(clntsock, clntaddr)
        return fd

    def stop(self, fd):
        clnt = by_fd[fd]
        clnt.close()
        if clnt.imei:
            del self.by_imei[clnt.imei]
        del self.by_fd[fd]

    def recv(self, fd):
        clnt = by_fd[fd]
        msg = clnt.recv()
        if isinstance(msg, LOGIN):
            self.by_imei[clnt.imei] = clnt
        return clnt.imei, msg

    def response(self, zmsg):
        if zmsg.imei in self.by_imei:
            clnt = self.by_imei[zmsg.imei].send(zmsg.payload)


def runserver(opts, conf):
    zctx = zmq.Context()
    zpub = zctx.socket(zmq.PUB)
    zpub.bind(conf.get("collector", "publishurl"))
    zsub = zctx.socket(zmq.SUB)
    zsub.connect(conf.get("collector", "listenurl"))
    tcpl = socket(AF_INET, SOCK_STREAM)
    tcpl.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    tcpl.bind(("", conf.getint("collector", "port")))
    tcpl.listen(5)
    tcpfd = tcpl.fileno()
    poller = zmq.Poller()
    poller.register(zsub, flags=zmq.POLLIN)
    poller.register(tcpfd, flags=zmq.POLLIN)
    clients = Clients()
    try:
        while True:
            tosend = []
            topoll = []
            tostop = []
            events = poller.poll(10)
            for sk, fl in events:
                if sk is zsub:
                    while True:
                        try:
                            msg = zsub.recv(zmq.NOBLOCK)
                            tosend.append(Zmsg(msg))
                        except zmq.Again:
                            break
                elif sk == tcpfd:
                    clntsock, clntaddr = ctlsock.accept()
                    topoll.append((clntsock, clntaddr))
                else:
                    imei, msg = clients.recv(sk)
                    zpub.send(Bcast(imei, msg).as_bytes)
                    if msg is None or isinstance(msg, HIBERNATION):
                        tostop.append(sk)
            # poll queue consumed, make changes now
            for fd in tostop:
                clients.stop(fd)
                pollset.unregister(fd)
            for zmsg in tosend:
                clients.response(zmsg)
            for clntsock, clntaddr in topoll:
                fd = clients.add(clntsock, clntaddr)
                pollset.register(fd)
    except KeyboardInterrupt:
        pass


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
    runserver(opts, conf)
