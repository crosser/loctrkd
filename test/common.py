""" Common housekeeping for tests that rely on daemons """

from configparser import ConfigParser, SectionProxy
from contextlib import closing, ExitStack
from http.server import HTTPServer, SimpleHTTPRequestHandler
from importlib import import_module
from logging import DEBUG, StreamHandler
from multiprocessing import Process
from os import kill, unlink
from signal import SIGINT
from socket import (
    AF_INET,
    AF_INET6,
    getaddrinfo,
    MSG_DONTWAIT,
    SOCK_DGRAM,
    SOCK_STREAM,
    SOL_SOCKET,
    SO_REUSEADDR,
    socket,
    SocketType,
)
from sys import exit, stderr
from random import Random
from tempfile import mkstemp
from time import sleep
from typing import Any, Optional
from unittest import TestCase

from loctrkd.common import init_protocols

NUMPORTS = 3


class TestWithServers(TestCase):
    def setUp(
        self, *args: str, httpd: bool = False, verbose: bool = False
    ) -> None:
        freeports = []
        with ExitStack() as stack:
            for _ in range(NUMPORTS):
                sk = stack.enter_context(closing(socket(AF_INET6, SOCK_DGRAM)))
                sk.bind(("", 0))
                sk.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
                freeports.append(sk.getsockname()[1])
        _, self.tmpfilebase = mkstemp()
        self.conf = ConfigParser()
        self.conf["common"] = {
            "protocols": "zx303proto,beesure",
        }
        self.conf["collector"] = {
            "port": str(freeports[0]),
            "publishurl": "ipc://" + self.tmpfilebase + ".pub",
            "listenurl": "ipc://" + self.tmpfilebase + ".pul",
        }
        self.conf["storage"] = {
            "dbfn": self.tmpfilebase + ".storage.sqlite",
            "events": "yes",
        }
        self.conf["opencellid"] = {
            "dbfn": self.tmpfilebase + ".opencellid.sqlite",
            "downloadurl": f"http://localhost:{freeports[2]}/test/262.csv.gz",
        }
        self.conf["rectifier"] = {
            "lookaside": "opencellid",
            "publishurl": "ipc://" + self.tmpfilebase + ".rect.pub",
        }
        self.conf["wsgateway"] = {
            "port": str(freeports[1]),
        }
        init_protocols(self.conf)
        self.children = []
        for srvname in args:
            if srvname == "collector":
                kwargs = {"handle_hibernate": False}
            else:
                kwargs = {}
            cls = import_module("loctrkd." + srvname, package=".")
            if verbose:
                cls.log.addHandler(StreamHandler(stderr))
                cls.log.setLevel(DEBUG)
            p = Process(target=cls.runserver, args=(self.conf,), kwargs=kwargs)
            p.start()
            self.children.append((srvname, p))
        if httpd:
            server = HTTPServer(("", freeports[2]), SimpleHTTPRequestHandler)

            def run(server: HTTPServer) -> None:
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    # TODO: this still leaves unclosed socket in the server
                    server.shutdown()

            p = Process(target=run, args=(server,))
            p.start()
            self.children.append(("httpd", p))
        sleep(1)

    def tearDown(self) -> None:
        for srvname, p in self.children:
            if p.pid is not None:
                kill(p.pid, SIGINT)
            p.join()
            self.assertEqual(
                p.exitcode,
                0,
                f"{srvname} terminated with return code {p.exitcode}",
            )
        for sfx in (
            "",
            ".pub",
            ".rect.pub",
            ".pul",
            ".storage.sqlite",
            ".opencellid.sqlite",
        ):
            try:
                unlink(self.tmpfilebase + sfx)
            except OSError:
                pass


class Fuzz(TestWithServers):
    def setUp(self, *args: str, **kwargs: Any) -> None:
        super().setUp("collector")
        self.rnd = Random()
        for fam, typ, pro, cnm, skadr in getaddrinfo(
            "127.0.0.1",
            self.conf.getint("collector", "port"),
            family=AF_INET,
            type=SOCK_STREAM,
        ):
            break  # Just take the first element
        self.sock = socket(AF_INET, SOCK_STREAM)
        self.sock.connect(skadr)

    def tearDown(self) -> None:
        sleep(1)  # give collector some time
        send_and_drain(self.sock, None)
        self.sock.close()
        sleep(1)  # Let the server close their side
        super().tearDown()


def send_and_drain(sock: SocketType, buf: Optional[bytes]) -> None:
    if buf is not None:
        sock.send(buf)
    try:
        sock.recv(4096, MSG_DONTWAIT)
    except BlockingIOError:
        pass
