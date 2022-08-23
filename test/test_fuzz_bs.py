""" Send junk to the collector """

import unittest
from .common import send_and_drain, TestWithServers, Fuzz

REPEAT: int = 1000000


class FuzzMsgs(Fuzz):
    def test_msgs(self) -> None:
        imeis = list(
            self.rnd.randint(1000000000, 9999999999) for _ in range(3)
        )
        for _ in range(REPEAT):
            base_size = self.rnd.randint(0, 5000)
            size = base_size + (
                (self.rnd.randint(-5, 5) // 5) * self.rnd.randint(1, 20)
            )
            if size < 0:
                size = 0
            imei = f"{self.rnd.choice(imeis):d}".encode("ascii")
            commapos = self.rnd.randint(0, 10)
            if commapos > 0 and commapos < base_size:
                payload = (
                    self.rnd.randbytes(commapos - 1)
                    + b","
                    + self.rnd.randbytes(base_size - commapos)
                )
            else:
                payload = self.rnd.randbytes(base_size)
            # print(imei, base_size, size)
            # "\[(\w\w)\*(\d{10})\*([0-9a-fA-F]{4})\*"
            buf = (
                b"[TS*"
                + imei
                + b"*"
                + f"{size:04x}".encode("ascii")
                + b"*"
                + self.rnd.randbytes(base_size)
                + b"]"
            )
            # print(buf[:64], "len:", len(buf))
            send_and_drain(self.sock, buf)


if __name__ == "__main__":
    unittest.main()
