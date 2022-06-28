""" TCP server that communicates with terminals """

from configparser import ConfigParser
from logging import getLogger
from os import umask
from socket import (
    socket,
    AF_INET6,
    SOCK_STREAM,
    SOL_SOCKET,
    SO_KEEPALIVE,
    SO_REUSEADDR,
)
from struct import pack
from time import time
from typing import Dict, List, Optional, Tuple
import zmq

from . import common
from .gps303proto import (
    GPS303Conn,
    StreamError,
    HIBERNATION,
    LOGIN,
    inline_response,
    parse_message,
    proto_of_message,
)
from .zmsg import Bcast, Resp

log = getLogger("gps303/collector")

MAXBUFFER: int = 4096


class Client:
    """Connected socket to the terminal plus buffer and metadata"""

    def __init__(self, sock: socket, addr: Tuple[str, int]) -> None:
        self.sock = sock
        self.addr = addr
        self.stream = GPS303Conn()
        self.imei: Optional[str] = None

    def close(self) -> None:
        log.debug("Closing fd %d (IMEI %s)", self.sock.fileno(), self.imei)
        self.sock.close()
        rest = self.stream.close()
        if rest:
            log.warning("%d bytes in buffer on close: %s", len(rest), rest)

    def recv(self) -> Optional[List[Tuple[float, Tuple[str, int], bytes]]]:
        """Read from the socket and parse complete messages"""
        try:
            segment = self.sock.recv(MAXBUFFER)
        except OSError as e:
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
        while True:
            try:
                return [
                    (when, self.addr, packet)
                    for packet in self.stream.recv(segment)
                ]
            except StreamError as e:
                log.warning(
                    "%s from fd %d (IMEI %s)", e, self.sock.fileno(), self.imei
                )

    def send(self, buffer: bytes) -> None:
        try:
            self.sock.send(self.stream.enframe(buffer))
        except OSError as e:
            log.error(
                "Sending to fd %d (IMEI %s): %s",
                self.sock.fileno(),
                self.imei,
                e,
            )

    def set_imei(self, imei: str) -> None:
        self.imei = imei


class Clients:
    def __init__(self) -> None:
        self.by_fd: Dict[int, Client] = {}
        self.by_imei: Dict[str, Client] = {}

    def add(self, clntsock: socket, clntaddr: Tuple[str, int]) -> int:
        fd = clntsock.fileno()
        log.info("Start serving fd %d from %s", fd, clntaddr)
        self.by_fd[fd] = Client(clntsock, clntaddr)
        return fd

    def stop(self, fd: int) -> None:
        clnt = self.by_fd[fd]
        log.info("Stop serving fd %d (IMEI %s)", clnt.sock.fileno(), clnt.imei)
        clnt.close()
        if clnt.imei:
            del self.by_imei[clnt.imei]
        del self.by_fd[fd]

    def recv(
        self, fd: int
    ) -> Optional[List[Tuple[Optional[str], float, Tuple[str, int], bytes]]]:
        clnt = self.by_fd[fd]
        msgs = clnt.recv()
        if msgs is None:
            return None
        result = []
        for when, peeraddr, packet in msgs:
            if proto_of_message(packet) == LOGIN.PROTO:
                msg = parse_message(packet)
                if isinstance(msg, LOGIN):  # Can be unparseable
                    if clnt.imei is None:
                        clnt.imei = msg.imei
                        log.info(
                            "LOGIN from fd %d (IMEI %s)",
                            clnt.sock.fileno(),
                            clnt.imei,
                        )
                        oldclnt = self.by_imei.get(clnt.imei)
                        if oldclnt is not None:
                            log.info(
                                "Orphaning fd %d with the same IMEI",
                                oldclnt.sock.fileno(),
                            )
                            oldclnt.imei = None
                    self.by_imei[clnt.imei] = clnt
                else:
                    log.warning(
                        "Login message from %s: %s, but client imei unfilled",
                        peeraddr,
                        packet,
                    )
            result.append((clnt.imei, when, peeraddr, packet))
            log.debug(
                "Received from %s (IMEI %s): %s",
                peeraddr,
                clnt.imei,
                packet.hex(),
            )
        return result

    def response(self, resp: Resp) -> None:
        if resp.imei in self.by_imei:
            self.by_imei[resp.imei].send(resp.packet)
        else:
            log.info("Not connected (IMEI %s)", resp.imei)


def runserver(conf: ConfigParser, handle_hibernate: bool = True) -> None:
    # Is this https://github.com/zeromq/pyzmq/issues/1627 still not fixed?!
    zctx = zmq.Context()  # type: ignore
    zpub = zctx.socket(zmq.PUB)  # type: ignore
    zpull = zctx.socket(zmq.PULL)  # type: ignore
    oldmask = umask(0o117)
    zpub.bind(conf.get("collector", "publishurl"))
    zpull.bind(conf.get("collector", "listenurl"))
    umask(oldmask)
    tcpl = socket(AF_INET6, SOCK_STREAM)
    tcpl.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    tcpl.bind(("", conf.getint("collector", "port")))
    tcpl.listen(5)
    tcpfd = tcpl.fileno()
    poller = zmq.Poller()  # type: ignore
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
                    clntsock.setsockopt(SOL_SOCKET, SO_KEEPALIVE, 1)
                    topoll.append((clntsock, clntaddr))
                elif fl & zmq.POLLIN:
                    received = clients.recv(sk)
                    if received is None:
                        log.debug("Terminal gone from fd %d", sk)
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
                            if proto == HIBERNATION.PROTO and handle_hibernate:
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
            for fd in tostop:
                poller.unregister(fd)  # type: ignore
                clients.stop(fd)
            for clntsock, clntaddr in topoll:
                fd = clients.add(clntsock, clntaddr)
                poller.register(fd, flags=zmq.POLLIN)
    except KeyboardInterrupt:
        zpub.close()
        zpull.close()
        zctx.destroy()  # type: ignore
        tcpl.close()


if __name__.endswith("__main__"):
    runserver(common.init(log))
