""" Send junk to the collector """

import unittest
from .common import send_and_drain, TestWithServers, Fuzz

REPEAT: int = 1000000


class FuzzMsgs(Fuzz):
    def test_msgs(self) -> None:
        for _ in range(REPEAT):
            size = self.rnd.randint(0, 300)
            buf = b"xx" + self.rnd.randbytes(size) + b"\r\n"
            send_and_drain(self.sock, buf)


if __name__ == "__main__":
    unittest.main()
