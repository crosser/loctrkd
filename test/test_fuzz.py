""" Send junk to the collector """

from random import Random
from socket import getaddrinfo, socket, AF_INET6, MSG_DONTWAIT, SOCK_STREAM
import unittest
from .common import TestWithServers

REPEAT: int = 1000000


class Fuzz(TestWithServers):
    def setUp(self, *args: str) -> None:
        super().setUp("collector")
        self.rnd = Random()
        for fam, typ, pro, cnm, skadr in getaddrinfo(
            "::1",
            self.conf.getint("collector", "port"),
            family=AF_INET6,
            type=SOCK_STREAM,
        ):
            break  # Just take the first element
        self.sock = socket(AF_INET6, SOCK_STREAM)
        self.sock.connect(skadr)

    def tearDown(self) -> None:
        self.sock.close()
        print("finished fuzzing")
        super().tearDown()

    def test_fuzz(self) -> None:
        for _ in range(REPEAT):
            size = self.rnd.randint(1, 5000)
            buf = self.rnd.randbytes(size)
            self.sock.send(buf)
            try:
                self.sock.recv(4096, MSG_DONTWAIT)
            except BlockingIOError:
                pass


if __name__ == "__main__":
    unittest.main()
