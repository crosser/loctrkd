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
        with closing(socket(AF_INET6, SOCK_DGRAM)) as sock:
            sock.bind(("", 0))
            sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
            freeport = sock.getsockname()[1]
        _, self.tmpfilebase = mkstemp()
        self.conf = ConfigParser()
        self.conf["collector"] = {
            "port": str(freeport),
            "publishurl": "ipc://" + self.tmpfilebase + ".pub",
            "listenurl": "ipc://" + self.tmpfilebase + ".pul",
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
        sleep(1)
        for srvname, p in self.children:
            if p.pid is not None:
                kill(p.pid, SIGINT)
            p.join()
            self.assertEqual(
                p.exitcode,
                0,
                srvname + " terminated with non-zero return code",
            )
        for sfx in (".pub", ".pul"):
            unlink(self.tmpfilebase + sfx)


def send_and_drain(sock: SocketType, buf: Optional[bytes]) -> None:
    if buf is not None:
        sock.send(buf)
    try:
        sock.recv(4096, MSG_DONTWAIT)
    except BlockingIOError:
        pass
