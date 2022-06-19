""" Common housekeeping for tests that rely on daemons """

from configparser import ConfigParser, SectionProxy
from contextlib import closing
from importlib import import_module
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
from tempfile import mkstemp
from time import sleep
from typing import Optional
from unittest import TestCase


class TestWithServers(TestCase):
    def setUp(self, *args: str) -> None:
        with closing(socket(AF_INET6, SOCK_DGRAM)) as sock1, closing(
            socket(AF_INET6, SOCK_DGRAM)
        ) as sock2:
            freeports = []
            for sock in sock1, sock2:
                sock.bind(("", 0))
                sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
                freeports.append(sock.getsockname()[1])
        _, self.tmpfilebase = mkstemp()
        self.conf = ConfigParser()
        self.conf["collector"] = {
            "port": str(freeports[0]),
            "publishurl": "ipc://" + self.tmpfilebase + ".pub",
            "listenurl": "ipc://" + self.tmpfilebase + ".pul",
        }
        self.conf["storage"] = {
            "dbfn": self.tmpfilebase + ".storage.sqlite",
        }
        self.conf["opencellid"] = {
            "dbfn": self.tmpfilebase + ".opencellid.sqlite",
        }
        self.conf["lookaside"] = {
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
            cls = import_module("gps303." + srvname, package=".")
            p = Process(target=cls.runserver, args=(self.conf,), kwargs=kwargs)
            p.start()
            self.children.append((srvname, p))
        sleep(1)

    def tearDown(self) -> None:
        for srvname, p in self.children:
            if p.pid is not None:
                kill(p.pid, SIGINT)
            p.join()
            self.assertEqual(
                p.exitcode,
                0,
                srvname + " terminated with non-zero return code",
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
