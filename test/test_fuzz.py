""" Send junk to the collector """

from random import Random
from socket import getaddrinfo, socket, AF_INET6, SOCK_STREAM
from unittest import TestCase

REPEAT: int = 1000000


class Fuzz(TestCase):
    def setUp(self) -> None:
        self.rnd = Random()
        for fam, typ, pro, cnm, skadr in getaddrinfo(
            "::1",
            4303,
            family=AF_INET6,
            type=SOCK_STREAM,
        ):
            break  # Just take the first element
        self.sock = socket(AF_INET6, SOCK_STREAM)
        self.sock.connect(skadr)

    def tearDown(self) -> None:
        self.sock.close()

    def test_fuzz(self) -> None:
        for _ in range(REPEAT):
            size = self.rnd.randint(1, 5000)
            buf = self.rnd.randbytes(size)
            self.sock.send(buf)
