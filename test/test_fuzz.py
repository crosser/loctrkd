""" Send junk to the collector """

from random import Random
from socket import getaddrinfo, socket, AF_INET6, SOCK_STREAM
from time import sleep
import unittest
from .common import send_and_drain, TestWithServers

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
        sleep(1)  # give collector some time
        send_and_drain(self.sock, None)
        self.sock.close()
        print("finished fuzzing")
        super().tearDown()

    def test_stream(self) -> None:
        for _ in range(REPEAT):
            size = self.rnd.randint(1, 5000)
            buf = self.rnd.randbytes(size)
            send_and_drain(self.sock, buf)

    def test_msgs(self) -> None:
        for _ in range(REPEAT):
            size = self.rnd.randint(0, 300)
            buf = b"xx" + self.rnd.randbytes(size) + b"\r\n"
            send_and_drain(self.sock, buf)


if __name__ == "__main__":
    unittest.main()
