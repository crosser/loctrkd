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
    AF_INET6,
    MSG_DONTWAIT,
    SOCK_DGRAM,
    SOL_SOCKET,
    SO_REUSEADDR,
    socket,
    SocketType,
)
from sys import exit, stderr
from tempfile import mkstemp
from time import sleep
from typing import Optional
from unittest import TestCase

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
        self.conf["collector"] = {
            "port": str(freeports[0]),
            "publishurl": "ipc://" + self.tmpfilebase + ".pub",
            "listenurl": "ipc://" + self.tmpfilebase + ".pul",
            "protocols": "zx303proto",
        }
        self.conf["storage"] = {
            "dbfn": self.tmpfilebase + ".storage.sqlite",
        }
        self.conf["opencellid"] = {
            "dbfn": self.tmpfilebase + ".opencellid.sqlite",
            "downloadurl": f"http://localhost:{freeports[2]}/test/262.csv.gz",
        }
        self.conf["rectifier"] = {
            "backend": "opencellid",
        }
        self.conf["wsgateway"] = {
            "port": str(freeports[1]),
        }
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
            ".pul",
            ".storage.sqlite",
            ".opencellid.sqlite",
        ):
            try:
                unlink(self.tmpfilebase + sfx)
            except OSError:
                pass


def send_and_drain(sock: SocketType, buf: Optional[bytes]) -> None:
    if buf is not None:
        sock.send(buf)
    try:
        sock.recv(4096, MSG_DONTWAIT)
    except BlockingIOError:
        pass
