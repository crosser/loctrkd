""" Websocket Gateway """

from logging import getLogger
from socket import socket, AF_INET6, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
from time import time
from wsproto import ConnectionType, WSConnection
from wsproto.events import AcceptConnection, CloseConnection, Message, Ping, Request, TextMessage
import zmq

from . import common
from .zmsg import LocEvt

log = getLogger("gps303/wsgateway")


class Client:
    """Websocket connection to the client"""

    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self.ws = WSConnection(ConnectionType.SERVER)
        self.ws_data = b""

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
        self.ws.receive_data(data)
        msgs = []
        for event in self.ws.events():
            if isinstance(event, Request):
                log.debug("WebSocket upgrade on fd %d", self.sock.fileno())
                #self.ws_data += self.ws.send(event.response())  # Why not?!
                self.ws_data += self.ws.send(AcceptConnection())
            elif isinstance(event, (CloseConnection, Ping)):
                log.debug("%s on fd %d", event, self.sock.fileno())
                self.ws_data += self.ws.send(event.response())
            elif isinstance(event, TextMessage):
                # TODO: save imei "subscription"
                log.debug("%s on fd %d", event, self.sock.fileno())
                msgs.append(event.data)
            else:
                log.warning("%s on fd %d", event, self.sock.fileno())
        if self.ws_data:  # Temp hack
            self.write()
        return msgs

    def send(self, imei, message):
        # TODO: filter only wanted imei got from the client
        self.ws_data += self.ws.send(Message(data=message))

    def write(self):
        try:
            sent = self.sock.send(self.ws_data)
            self.ws_data = self.ws_data[sent:]
        except OSError as e:
            log.error(
                "Sending to fd %d (IMEI %s): %s",
                self.sock.fileno(),
                self.imei,
                e,
            )
            self.ws_data = b""


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
        return result

    def send(self, msgs):
        for clnt in self.by_fd.values():
            clnt.send(msgs)
            clnt.write()

def runserver(conf):
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
        while True:
            tosend = []
            topoll = []
            tostop = []
            events = poller.poll(1000)
            for sk, fl in events:
                if sk is zsub:
                    while True:
                        try:
                            msg = zsub.recv(zmq.NOBLOCK)
                            tosend.append(LocEvt(msg))
                        except zmq.Again:
                            break
                elif sk == tcpfd:
                    clntsock, clntaddr = tcpl.accept()
                    topoll.append((clntsock, clntaddr))
                elif fl & zmq.POLLIN:
                    received = clients.recv(sk)
                    if received is None:
                        log.debug(
                            "Client gone from fd %d", sk
                        )
                        tostop.append(sk)
                    else:
                        for msg in received:
                            log.debug("Received from %d: %s", sk, msg)
                else:
                    log.debug("Stray event: %s on socket %s", fl, sk)
            # poll queue consumed, make changes now
            for fd in tostop:
                poller.unregister(fd)
                clients.stop(fd)
            for zmsg in tosend:
                log.debug("Sending to the client: %s", zmsg)
                clients.send(zmsg)
            for clntsock, clntaddr in topoll:
                fd = clients.add(clntsock, clntaddr)
                poller.register(fd, flags=zmq.POLLIN)
            # TODO: Handle write overruns (register for POLLOUT)
    except KeyboardInterrupt:
        pass


if __name__.endswith("__main__"):
    runserver(common.init(log))
