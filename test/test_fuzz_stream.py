""" Send junk to the collector """

import unittest
from .common import send_and_drain, TestWithServers, Fuzz

REPEAT: int = 1000000


class FuzzStream(Fuzz):
    def test_stream(self) -> None:
        for _ in range(REPEAT):
            size = self.rnd.randint(1, 5000)
            buf = self.rnd.randbytes(size)
            send_and_drain(self.sock, buf)


if __name__ == "__main__":
    unittest.main()
