""" Websocket Gateway """

from configparser import ConfigParser
from datetime import datetime, timezone
from importlib import import_module
from json import dumps, loads
from logging import getLogger
from socket import socket, AF_INET6, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
from time import time
from typing import Any, cast, Dict, List, Optional, Set, Tuple
from wsproto import ConnectionType, WSConnection
from wsproto.events import (
    AcceptConnection,
    CloseConnection,
    Event,
    Message,
    Ping,
    Request,
    TextMessage,
)
from wsproto.utilities import RemoteProtocolError
import zmq

from . import common
from .evstore import initdb, fetch, fetchpmod
from .protomodule import ProtoModule
from .zmsg import Rept, Resp, rtopic

log = getLogger("loctrkd/wsgateway")

htmlfile = None


def backlog(imei: str, numback: int) -> List[Dict[str, Any]]:
    result = []
    for report in fetch(imei, numback):
        report["type"] = "location"
        timestamp = report.pop("devtime")
        report["timestamp"] = timestamp
        result.append(report)
    return result


def try_http(data: bytes, fd: int, e: Exception) -> bytes:
    global htmlfile
    try:
        lines = data.decode().split("\r\n")
        request = lines[0]
        headers = lines[1:]
        op, resource, proto = request.split(" ")
        log.debug(
            "HTTP %s for %s, proto %s from fd %d, headers: %s",
            op,
            resource,
            proto,
            fd,
            headers,
        )
        if op == "GET":
            if htmlfile is None:
                return (
                    f"{proto} 500 No data configured\r\n"
                    f"Content-Type: text/plain\r\n\r\n"
                    f"HTML data not configured on the server\r\n".encode()
                )
            else:
                try:
                    with open(htmlfile, "rb") as fl:
                        htmldata = fl.read()
                    length = len(htmldata)
                    return (
                        f"{proto} 200 Ok\r\n"
                        f"Content-Type: text/html; charset=utf-8\r\n"
                        f"Content-Length: {len(htmldata):d}\r\n\r\n"
                    ).encode("utf-8") + htmldata
                except OSError:
                    return (
                        f"{proto} 500 File not found\r\n"
                        f"Content-Type: text/plain\r\n\r\n"
                        f"HTML file could not be opened\r\n".encode()
                    )
        else:
            return (
                f"{proto} 400 Bad request\r\n"
                "Content-Type: text/plain\r\n\r\n"
                "Bad request\r\n".encode()
            )
    except ValueError:
        log.warning("Unparseable data from fd %d: %s", fd, data)
        raise e


class Client:
    """Websocket connection to the client"""

    def __init__(self, sock: socket, addr: Tuple[str, int]) -> None:
        self.sock = sock
        self.addr = addr
        self.ws = WSConnection(ConnectionType.SERVER)
        self.ws_data = b""
        self.ready = False
        self.imeis: Set[str] = set()

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(fd={self.sock.fileno()}, addr={self.addr})"

    def close(self) -> None:
        log.debug("Closing fd %d", self.sock.fileno())
        self.sock.close()

    def recv(self) -> Optional[List[Dict[str, Any]]]:
        try:
            data = self.sock.recv(4096)
        except OSError as e:
            log.warning(
                "Reading from fd %d: %s",
                self.sock.fileno(),
                e,
            )
            self.ws.receive_data(None)
            return None
        if not data:  # Client has closed connection
            log.info(
                "EOF reading from fd %d",
                self.sock.fileno(),
            )
            self.ws.receive_data(None)
            return None
        try:
            self.ws.receive_data(data)
        except RemoteProtocolError as e:
            log.debug(
                "Websocket error on fd %d, try plain http (%s)",
                self.sock.fileno(),
                e,
            )
            self.ws_data = try_http(data, self.sock.fileno(), e)
            # this `write` is a hack - writing _ought_ to be done at the
            # stage when all other writes are performed. But I could not
            # arrange it so in a logical way. Let it stay this way. The
            # whole http server affair is a hack anyway.
            self.write()
            log.debug("Sending HTTP response to %d", self.sock.fileno())
            msgs = None
        else:
            msgs = []
            for event in self.ws.events():
                if isinstance(event, Request):
                    log.debug("WebSocket upgrade on fd %d", self.sock.fileno())
                    # self.ws_data += self.ws.send(event.response())  # Why not?!
                    self.ws_data += self.ws.send(AcceptConnection())
                    self.ready = True
                elif isinstance(event, (CloseConnection, Ping)):
                    log.debug("%s on fd %d", event, self.sock.fileno())
                    self.ws_data += self.ws.send(event.response())
                elif isinstance(event, TextMessage):
                    log.debug("%s on fd %d", event, self.sock.fileno())
                    msg = loads(event.data)
                    msgs.append(msg)
                    if msg.get("type", None) == "subscribe":
                        self.imeis = set(msg.get("imei", []))
                        log.debug(
                            "subs list on fd %s is %s",
                            self.sock.fileno(),
                            self.imeis,
                        )
                else:
                    log.warning("%s on fd %d", event, self.sock.fileno())
        return msgs

    def wants(self, imei: str) -> bool:
        log.debug(
            "wants %s? set is %s on fd %d",
            imei,
            self.imeis,
            self.sock.fileno(),
        )
        return imei in self.imeis

    def send(self, message: Dict[str, Any]) -> None:
        if self.ready and message["imei"] in self.imeis:
            self.ws_data += self.ws.send(Message(data=dumps(message)))

    def write(self) -> bool:
        if self.ws_data:
            try:
                sent = self.sock.send(self.ws_data)
                self.ws_data = self.ws_data[sent:]
            except OSError as e:
                log.error(
                    "Sending to fd %d: %s",
                    self.sock.fileno(),
                    e,
                )
                self.ws_data = b""
        return bool(self.ws_data)


class Clients:
    def __init__(self) -> None:
        self.by_fd: Dict[int, Client] = {}

    def add(self, clntsock: socket, clntaddr: Tuple[str, int]) -> int:
        fd = clntsock.fileno()
        log.info("Start serving fd %d from %s", fd, clntaddr)
        self.by_fd[fd] = Client(clntsock, clntaddr)
        return fd

    def stop(self, fd: int) -> None:
        clnt = self.by_fd[fd]
        log.info("Stop serving fd %d", clnt.sock.fileno())
        clnt.close()
        del self.by_fd[fd]

    def recv(self, fd: int) -> Tuple[Client, Optional[List[Dict[str, Any]]]]:
        clnt = self.by_fd[fd]
        return (clnt, clnt.recv())

    def send(self, clnt: Optional[Client], msg: Dict[str, Any]) -> Set[int]:
        towrite = set()
        if clnt is None:
            for fd, cl in self.by_fd.items():
                if cl.wants(msg["imei"]):
                    cl.send(msg)
                    towrite.add(fd)
        else:
            fd = clnt.sock.fileno()
            if self.by_fd.get(fd, None) == clnt:
                clnt.send(msg)
                towrite.add(fd)
            else:
                log.info(
                    "Trying to send %s to client at %d, not in service",
                    msg,
                    fd,
                )
        return towrite

    def write(self, towrite: Set[int]) -> Set[int]:
        waiting = set()
        for fd, clnt in [(fd, self.by_fd.get(fd)) for fd in towrite]:
            if clnt and clnt.write():
                waiting.add(fd)
        return waiting

    def subs(self) -> Set[str]:
        result = set()
        for clnt in self.by_fd.values():
            result |= clnt.imeis
        return result


def sendcmd(zpush: Any, wsmsg: Dict[str, Any]) -> Dict[str, Any]:
    imei = wsmsg.pop("imei", None)
    cmd = wsmsg.pop("type", None)
    if imei is None or cmd is None:
        log.info("Unhandled message %s %s %s", cmd, imei, wsmsg)
        return {
            "type": "cmdresult",
            "imei": imei,
            "result": "Did not get imei or cmd",
        }
    pmod = fetchpmod(imei)
    if pmod is None:
        log.info("Uknown type of recipient for %s %s %s", cmd, imei, wsmsg)
        return {
            "type": "cmdresult",
            "imei": imei,
            "result": "Type of the terminal is unknown",
        }
    tmsg = common.make_response(pmod, cmd, imei, **wsmsg)
    if tmsg is None:
        log.info("Could not make packet for %s %s %s", cmd, imei, wsmsg)
        return {
            "type": "cmdresult",
            "imei": imei,
            "result": f"{cmd} unimplemented for terminal protocol {pmod}",
        }
    resp = Resp(imei=imei, when=time(), packet=tmsg.packed)
    log.debug("Response: %s", resp)
    zpush.send(resp.packed)
    return {
        "type": "cmdresult",
        "imei": imei,
        "result": f"{cmd} sent to {imei}",
    }


def runserver(conf: ConfigParser) -> None:
    global htmlfile
    initdb(conf.get("storage", "dbfn"))
    htmlfile = conf.get("wsgateway", "htmlfile", fallback=None)
    # Is this https://github.com/zeromq/pyzmq/issues/1627 still not fixed?!
    zctx = zmq.Context()  # type: ignore
    zsub = zctx.socket(zmq.SUB)  # type: ignore
    zsub.connect(conf.get("rectifier", "publishurl"))
    zpush = zctx.socket(zmq.PUSH)  # type: ignore
    zpush.connect(conf.get("collector", "listenurl"))
    tcpl = socket(AF_INET6, SOCK_STREAM)
    tcpl.setblocking(False)
    tcpl.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    tcpl.bind(("", conf.getint("wsgateway", "port")))
    tcpl.listen(5)
    tcpfd = tcpl.fileno()
    poller = zmq.Poller()  # type: ignore
    poller.register(zsub, flags=zmq.POLLIN)
    poller.register(tcpfd, flags=zmq.POLLIN)
    clients = Clients()
    activesubs: Set[str] = set()
    try:
        towait: Set[int] = set()
        while True:
            neededsubs = clients.subs()
            for imei in neededsubs - activesubs:
                zsub.setsockopt(zmq.SUBSCRIBE, rtopic(imei))
            for imei in activesubs - neededsubs:
                zsub.setsockopt(zmq.UNSUBSCRIBE, rtopic(imei))
            activesubs = neededsubs
            log.debug("Subscribed to: %s", activesubs)
            tosend: List[Tuple[Optional[Client], Dict[str, Any]]] = []
            topoll = []
            tostop = []
            towrite = set()
            events = poller.poll()
            for sk, fl in events:
                if sk is zsub:
                    while True:
                        try:
                            zmsg = Rept(zsub.recv(zmq.NOBLOCK))
                            msg = loads(zmsg.payload)
                            msg["imei"] = zmsg.imei
                            log.debug("Got %s, sending %s", zmsg, msg)
                            tosend.append((None, msg))
                        except zmq.Again:
                            break
                elif sk == tcpfd:
                    clntsock, clntaddr = tcpl.accept()
                    topoll.append((clntsock, clntaddr))
                elif fl & zmq.POLLIN:
                    clnt, received = clients.recv(sk)
                    if received is None:
                        log.debug("Client gone from fd %d", sk)
                        tostop.append(sk)
                        towait.discard(sk)
                    else:
                        for wsmsg in received:
                            log.debug("Received from %d: %s", sk, wsmsg)
                            if wsmsg.get("type", None) == "subscribe":
                                # Have to live w/o typeckeding from json
                                imeis = cast(List[str], wsmsg.get("imei"))
                                numback: int = wsmsg.get("backlog", 5)
                                for imei in imeis:
                                    tosend.extend(
                                        [
                                            (clnt, msg)
                                            for msg in backlog(imei, numback)
                                        ]
                                    )
                            else:
                                tosend.append((clnt, sendcmd(zpush, wsmsg)))
                        towrite.add(sk)
                elif fl & zmq.POLLOUT:
                    log.debug("Write now open for fd %d", sk)
                    towrite.add(sk)
                    towait.discard(sk)
                else:
                    log.debug("Stray event: %s on socket %s", fl, sk)
            # poll queue consumed, make changes now
            for fd in tostop:
                poller.unregister(fd)  # type: ignore
                clients.stop(fd)
            for towhom, wsmsg in tosend:
                log.debug("Sending to the client %s: %s", towhom, wsmsg)
                towrite |= clients.send(towhom, wsmsg)
            for clntsock, clntaddr in topoll:
                fd = clients.add(clntsock, clntaddr)
                poller.register(fd, flags=zmq.POLLIN)
            # Deal with actually writing the data out
            trywrite = towrite - towait
            morewait = clients.write(trywrite)
            log.debug(
                "towait %s, tried %s, still busy %s",
                towait,
                trywrite,
                morewait,
            )
            for fd in morewait - trywrite:  # new fds waiting for write
                poller.modify(fd, flags=zmq.POLLIN | zmq.POLLOUT)  # type: ignore
            for fd in trywrite - morewait:  # no longer waiting for write
                poller.modify(fd, flags=zmq.POLLIN)  # type: ignore
            towait &= trywrite
            towait |= morewait
    except KeyboardInterrupt:
        zsub.close()
        zctx.destroy()  # type: ignore
        tcpl.close()


if __name__.endswith("__main__"):
    runserver(common.init(log))
