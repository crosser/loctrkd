""" TCP server that communicates with terminals """

from getopt import getopt
from logging import getLogger, StreamHandler, DEBUG, INFO
from logging.handlers import SysLogHandler
from socket import socket, AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
from time import time
import sys
import zmq

from .config import readconfig
from .gps303proto import handle_packet, make_response, LOGIN, set_config

CONF = "/etc/gps303.conf"

log = getLogger("gps303/collector")


class Bcast:
    """Zmq message to broadcast what was received from the terminal"""
    def __init__(self, imei, msg):
        self.as_bytes = imei.encode() + msg.encode()


class Resp:
    """Zmq message received from a third party to send to the terminal"""
    def __init__(self, msg):
        self.imei = msg[:16].decode()
        self.payload = msg[16:]


class Client:
    """Connected socket to the terminal plus buffer and metadata"""
    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self.buffer = b""
        self.imei = None

    def close(self):
        log.debug("Closing fd %d (IMEI %s)", self.sock.fileno(), self.imei)
        self.sock.close()
        self.buffer = b""
        self.imei = None

    def recv(self):
        """ Read from the socket and parse complete messages """
        try:
            segment = self.sock.recv(4096)
        except OSError:
            log.warning("Reading from fd %d (IMEI %s): %s",
                    self.sock.fileno(), self.imei, e)
            return None
        if not segment:  # Terminal has closed connection
            log.info("EOF reading from fd %d (IMEI %s)",
                    self.sock.fileno(), self.imei)
            return None
        when = time()
        self.buffer += segment
        msgs = []
        while True:
            framestart = self.buffer.find(b"xx")
            if framestart == -1:  # No frames, return whatever we have
                break
            if framestart > 0:  # Should not happen, report
                log.warning("Undecodable data \"%s\" from fd %d (IMEI %s)",
                        self.buffer[:framestart].hex(), self.sock.fileno(), self.imei)
                self.buffer = self.buffer[framestart:]
            # At this point, buffer starts with a packet
            frameend = self.buffer.find(b"\r\n", 4)
            if frameend == -1:  # Incomplete frame, return what we have
                break
            msg = parse_message(self.buffer[:frameend])
            self.buffer = self.buffer[frameend+2:]
            if isinstance(msg, LOGIN):
                self.imei = msg.imei
                log.info("LOGIN from fd %d: IMEI %s",
                        self.sock.fileno(), self.imei)
            msgs.append(msg)
        return msgs

    def send(self, buffer):
        try:
            self.sock.send(b"xx" + buffer + b"\r\n")
        except OSError as e:
            log.error("Sending to fd %d (IMEI %s): %s",
                    self.sock.fileno, self.imei, e)

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
        log.info("Stop serving fd %d (IMEI %s)", clnt.sock.fileno(), clnt.imei)
        clnt.close()
        if clnt.imei:
            del self.by_imei[clnt.imei]
        del self.by_fd[fd]

    def recv(self, fd):
        clnt = by_fd[fd]
        msgs = clnt.recv()
        result = []
        for msg in msgs:
            if isinstance(msg, LOGIN):
                self.by_imei[clnt.imei] = clnt
            result.append(clnt.imei, msg)
        return result

    def response(self, resp):
        if resp.imei in self.by_imei:
            self.by_imei[resp.imei].send(resp.payload)


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
                            tosend.append(Resp(msg))
                        except zmq.Again:
                            break
                elif sk == tcpfd:
                    clntsock, clntaddr = ctlsock.accept()
                    topoll.append((clntsock, clntaddr))
                else:
                    imei, msg = clients.recv(sk)
                    zpub.send(Bcast(imei, msg).as_bytes)
                    if msg is None or isinstance(msg, HIBERNATION):
                        log.debug("HIBERNATION from fd %d", sk)
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
