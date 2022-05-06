""" Websocket Gateway """

from json import loads
from logging import getLogger
from socket import socket, AF_INET6, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
from time import time
from wsproto import ConnectionType, WSConnection
from wsproto.events import (
    AcceptConnection,
    CloseConnection,
    Message,
    Ping,
    Request,
    TextMessage,
)
from wsproto.utilities import RemoteProtocolError
import zmq

from . import common
from .zmsg import LocEvt

log = getLogger("gps303/wsgateway")
htmlfile = None


def try_http(data, fd, e):
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
        try:
            pos = resource.index("?")
            resource = resource[:pos]
        except ValueError:
            pass
        if op == "GET":
            if htmlfile is None:
                return (
                    f"{proto} 500 No data configured\r\n"
                    f"Content-Type: text/plain\r\n\r\n"
                    f"HTML data not configure on the server\r\n".encode()
                )
            elif resource == "/":
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
                    f"{proto} 404 File not found\r\n"
                    f"Content-Type: text/plain\r\n\r\n"
                    f'We can only serve "/"\r\n'.encode()
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

    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self.ws = WSConnection(ConnectionType.SERVER)
        self.ws_data = b""
        self.ready = False
        self.imeis = set()

    def close(self):
        log.debug("Closing fd %d", self.sock.fileno())
        self.sock.close()

    def recv(self):
        try:
            data = self.sock.recv(4096)
        except OSError:
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
            self.write()  # TODO this is a hack
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
                    # TODO: save imei "subscription"
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

    def wants(self, imei):
        log.debug("wants %s? set is %s on fd %d", imei, self.imeis, self.sock.fileno())
        return True  # TODO: check subscriptions

    def send(self, message):
        if self.ready and message.imei in self.imeis:
            self.ws_data += self.ws.send(Message(data=message.json))

    def write(self):
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
    def __init__(self):
        self.by_fd = {}

    def add(self, clntsock, clntaddr):
        fd = clntsock.fileno()
        log.info("Start serving fd %d from %s", fd, clntaddr)
        self.by_fd[fd] = Client(clntsock, clntaddr)
        return fd

    def stop(self, fd):
        clnt = self.by_fd[fd]
        log.info("Stop serving fd %d", clnt.sock.fileno())
        clnt.close()
        del self.by_fd[fd]

    def recv(self, fd):
        clnt = self.by_fd[fd]
        msgs = clnt.recv()
        if msgs is None:
            return None
        result = []
        for msg in msgs:
            log.debug("Received: %s", msg)
            result.append(msg)
        return result

    def send(self, msg):
        towrite = set()
        for fd, clnt in self.by_fd.items():
            if clnt.wants(msg.imei):
                clnt.send(msg)
                towrite.add(fd)
        return towrite

    def write(self, towrite):
        waiting = set()
        for fd, clnt in [(fd, self.by_fd.get(fd)) for fd in towrite]:
            if clnt.write():
                waiting.add(fd)
        return waiting


def runserver(conf):
    global htmlfile

    htmlfile = conf.get("wsgateway", "htmlfile")
    zctx = zmq.Context()
    zsub = zctx.socket(zmq.SUB)
    zsub.connect(conf.get("lookaside", "publishurl"))
    zsub.setsockopt(zmq.SUBSCRIBE, b"")
    tcpl = socket(AF_INET6, SOCK_STREAM)
    tcpl.setblocking(False)
    tcpl.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    tcpl.bind(("", conf.getint("wsgateway", "port")))
    tcpl.listen(5)
    tcpfd = tcpl.fileno()
    poller = zmq.Poller()
    poller.register(zsub, flags=zmq.POLLIN)
    poller.register(tcpfd, flags=zmq.POLLIN)
    clients = Clients()
    try:
        towait = set()
        while True:
            tosend = []
            topoll = []
            tostop = []
            towrite = set()
            events = poller.poll()
            for sk, fl in events:
                if sk is zsub:
                    while True:
                        try:
                            zmsg = LocEvt(zsub.recv(zmq.NOBLOCK))
                            tosend.append(zmsg)
                        except zmq.Again:
                            break
                elif sk == tcpfd:
                    clntsock, clntaddr = tcpl.accept()
                    topoll.append((clntsock, clntaddr))
                elif fl & zmq.POLLIN:
                    received = clients.recv(sk)
                    if received is None:
                        log.debug("Client gone from fd %d", sk)
                        tostop.append(sk)
                        towait.discard(fd)
                    else:
                        for msg in received:
                            log.debug("Received from %d: %s", sk, msg)
                        towrite.add(sk)
                elif fl & zmq.POLLOUT:
                    log.debug("Write now open for fd %d", sk)
                    towrite.add(sk)
                    towait.discard(sk)
                else:
                    log.debug("Stray event: %s on socket %s", fl, sk)
            # poll queue consumed, make changes now
            for fd in tostop:
                poller.unregister(fd)
                clients.stop(fd)
            for zmsg in tosend:
                log.debug("Sending to the clients: %s", zmsg)
                towrite |= clients.send(zmsg)
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
                poller.modify(fd, flags=zmq.POLLIN | zmq.POLLOUT)
            for fd in trywrite - morewait:  # no longer waiting for write
                poller.modify(fd, flags=zmq.POLLIN)
            towait &= trywrite
            towait |= morewait
    except KeyboardInterrupt:
        pass


if __name__.endswith("__main__"):
    runserver(common.init(log))
