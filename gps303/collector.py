""" TCP server that communicates with terminals """

from logging import getLogger
from os import umask
from socket import socket, AF_INET6, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
from time import time
from struct import pack
import zmq

from . import common
from .gps303proto import (
    HIBERNATION,
    LOGIN,
    inline_response,
    parse_message,
    proto_of_message,
)
from .zmsg import Bcast, Resp

log = getLogger("gps303/collector")


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

    def recv(self):
        """Read from the socket and parse complete messages"""
        try:
            segment = self.sock.recv(4096)
        except OSError:
            log.warning(
                "Reading from fd %d (IMEI %s): %s",
                self.sock.fileno(),
                self.imei,
                e,
            )
            return None
        if not segment:  # Terminal has closed connection
            log.info(
                "EOF reading from fd %d (IMEI %s)",
                self.sock.fileno(),
                self.imei,
            )
            return None
        when = time()
        self.buffer += segment
        msgs = []
        while True:
            framestart = self.buffer.find(b"xx")
            if framestart == -1:  # No frames, return whatever we have
                break
            if framestart > 0:  # Should not happen, report
                log.warning(
                    'Undecodable data "%s" from fd %d (IMEI %s)',
                    self.buffer[:framestart].hex(),
                    self.sock.fileno(),
                    self.imei,
                )
                self.buffer = self.buffer[framestart:]
            # At this point, buffer starts with a packet
            frameend = self.buffer.find(b"\r\n", 4)
            if frameend == -1:  # Incomplete frame, return what we have
                break
            packet = self.buffer[2:frameend]
            self.buffer = self.buffer[frameend + 2 :]
            if proto_of_message(packet) == LOGIN.PROTO:
                self.imei = parse_message(packet).imei
                log.info(
                    "LOGIN from fd %d (IMEI %s)", self.sock.fileno(), self.imei
                )
            msgs.append((when, self.addr, packet))
        return msgs

    def send(self, buffer):
        try:
            self.sock.send(b"xx" + buffer + b"\r\n")
        except OSError as e:
            log.error(
                "Sending to fd %d (IMEI %s): %s",
                self.sock.fileno,
                self.imei,
                e,
            )


class Clients:
    def __init__(self):
        self.by_fd = {}
        self.by_imei = {}

    def add(self, clntsock, clntaddr):
        fd = clntsock.fileno()
        log.info("Start serving fd %d from %s", fd, clntaddr)
        self.by_fd[fd] = Client(clntsock, clntaddr)
        return fd

    def stop(self, fd):
        clnt = self.by_fd[fd]
        log.info("Stop serving fd %d (IMEI %s)", clnt.sock.fileno(), clnt.imei)
        clnt.close()
        if clnt.imei:
            del self.by_imei[clnt.imei]
        del self.by_fd[fd]

    def recv(self, fd):
        clnt = self.by_fd[fd]
        msgs = clnt.recv()
        if msgs is None:
            return None
        result = []
        for when, peeraddr, packet in msgs:
            if proto_of_message(packet) == LOGIN.PROTO:  # Could do blindly...
                self.by_imei[clnt.imei] = clnt
            result.append((clnt.imei, when, peeraddr, packet))
            log.debug(
                "Received from %s (IMEI %s): %s",
                peeraddr,
                clnt.imei,
                packet.hex(),
            )
        return result

    def response(self, resp):
        if resp.imei in self.by_imei:
            self.by_imei[resp.imei].send(resp.packet)
        else:
            log.info("Not connected (IMEI %s)", resp.imei)


def runserver(conf):
    zctx = zmq.Context()
    zpub = zctx.socket(zmq.PUB)
    zpull = zctx.socket(zmq.PULL)
    oldmask = umask(0o117)
    zpub.bind(conf.get("collector", "publishurl"))
    zpull.bind(conf.get("collector", "listenurl"))
    umask(oldmask)
    tcpl = socket(AF_INET6, SOCK_STREAM)
    tcpl.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    tcpl.bind(("", conf.getint("collector", "port")))
    tcpl.listen(5)
    tcpfd = tcpl.fileno()
    poller = zmq.Poller()
    poller.register(zpull, flags=zmq.POLLIN)
    poller.register(tcpfd, flags=zmq.POLLIN)
    clients = Clients()
    try:
        while True:
            tosend = []
            topoll = []
            tostop = []
            events = poller.poll(1000)
            for sk, fl in events:
                if sk is zpull:
                    while True:
                        try:
                            msg = zpull.recv(zmq.NOBLOCK)
                            zmsg = Resp(msg)
                            tosend.append(zmsg)
                        except zmq.Again:
                            break
                elif sk == tcpfd:
                    clntsock, clntaddr = tcpl.accept()
                    topoll.append((clntsock, clntaddr))
                elif fl & zmq.POLLIN:
                    received = clients.recv(sk)
                    if received is None:
                        log.debug(
                            "Terminal gone from fd %d (IMEI %s)", sk, imei
                        )
                        tostop.append(sk)
                    else:
                        for imei, when, peeraddr, packet in received:
                            proto = proto_of_message(packet)
                            zpub.send(
                                Bcast(
                                    proto=proto,
                                    imei=imei,
                                    when=when,
                                    peeraddr=peeraddr,
                                    packet=packet,
                                ).packed
                            )
                            if proto == HIBERNATION.PROTO:
                                log.debug(
                                    "HIBERNATION from fd %d (IMEI %s)",
                                    sk,
                                    imei,
                                )
                                tostop.append(sk)
                            respmsg = inline_response(packet)
                            if respmsg is not None:
                                tosend.append(
                                    Resp(imei=imei, when=when, packet=respmsg)
                                )
                else:
                    log.debug("Stray event: %s on socket %s", fl, sk)
            # poll queue consumed, make changes now
            for fd in tostop:
                poller.unregister(fd)
                clients.stop(fd)
            for zmsg in tosend:
                zpub.send(
                    Bcast(
                        is_incoming=False,
                        proto=proto_of_message(zmsg.packet),
                        when=zmsg.when,
                        imei=zmsg.imei,
                        packet=zmsg.packet,
                    ).packed
                )
                log.debug("Sending to the client: %s", zmsg)
                clients.response(zmsg)
            for clntsock, clntaddr in topoll:
                fd = clients.add(clntsock, clntaddr)
                poller.register(fd, flags=zmq.POLLIN)
    except KeyboardInterrupt:
        pass


if __name__.endswith("__main__"):
    runserver(common.init(log))
