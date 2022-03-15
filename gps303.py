#!/usr/bin/env python3

from enum import Enum
from select import poll, POLLIN, POLLERR, POLLHUP, POLLPRI
from socket import socket, AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
from struct import pack, unpack
import sys
from time import time

PORT = 4303

class P(Enum):
    UNKNOWN = 0x00
    LOGIN = 0x01
    STATUS = 0x13
    HIBERNATION = 0x14
    time = 0x30
    SETUP = 0x57
    


def answer_setup(data):
    return bytes.fromhex("0300310000000000000000000000000000000000000000000000003b3b3b")

def handle_packet(packet, addr, when):
    xx, length, proto = unpack("!2sBB", packet[:4])
    crlf = packet[-2:]
    data = packet[4:-2]
    if xx != b"xx" or crlf != b"\r\n" or (length > 1 and len(packet) != length + 2):
        print("bad packet:", packet.hex())
    print("length", length, "proto", hex(proto))
    try:
        p = P(proto)
    except ValueError:
        p = P.UNKNOWN
    payload = b""
    if p == P.LOGIN:
    	print("imei", data[:-1].hex(), "ver", data[-1:].hex())
    elif p == P.SETUP:
        payload = answer_setup(data)
    length = len(payload)+1
    if length > 6:
        length -= 6
    return b"xx" + pack("B", length) + pack("B", proto) + payload + b"\r\n"

if __name__ == "__main__":
    ctlsock = socket(AF_INET, SOCK_STREAM)
    ctlsock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    ctlsock.bind(("", PORT))
    ctlsock.listen(5)
    ctlfd = ctlsock.fileno()
    pollset = poll()
    pollset.register(ctlfd, POLLIN | POLLERR | POLLHUP | POLLPRI)
    clnt_dict = {}
    while True:
        try:
            events = pollset.poll(1000)
        except KeyboardInterrupt:
            print("Exiting")
            sys.exit(0)
        for fd, ev in events:
            if fd == ctlfd:
                if ev & POLLIN:
                    clntsock, clntaddr = ctlsock.accept()
                    clntfd = clntsock.fileno()
                    clnt_dict[clntfd] = (clntsock, clntaddr)
                    pollset.register(clntfd, POLLIN | POLLERR | POLLHUP | POLLPRI)
                    print("accepted connection from", clntaddr, "fd", clntfd)
                if ev & ~POLLIN:
                    print("unexpected event on ctlfd:", ev)
            else:
                try:
                    clntsock, clntaddr = clnt_dict[fd]
                except KeyError:  # this socket closed already
                    continue
                if ev & POLLIN:
                    packet = clntsock.recv(4096)
                    when = time()
                    print("packet", packet, "from", clntaddr, "from fd", fd)
                    if packet:
                        response = handle_packet(packet, clntaddr, when)
                        if response:
                            try:
                                # Ignore possibility of blocking
                                clntsock.send(response)
                            except OSError as e:
                                print("sending to socket", fd, "error", e)
                    else:
                        print("disconnect")
                        pollset.unregister(fd)
                        clntsock.close()
                        del clnt_dict[fd]
                if ev & ~POLLIN:
                    print("unexpected event", ev, "on fd", fd)
