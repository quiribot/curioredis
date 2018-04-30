from .parser import Reader
from .errors import ConnectionClosedError


class Connection:
    def __init__(self, sock, encoding="utf-8", max_recv=2**16):
        self._sock = sock
        self._encoding = encoding
        self._reader = Reader(encoding=encoding)
        self._max_recv = max_recv

    async def send_command(self, *args):
        lines = []
        lines.append("*%d" % len(args))
        for arg in args:
            lines.append("$%d" % len(arg))
            lines.append(arg)
        data = ("\r\n".join(lines) + "\r\n").encode(self._encoding)
        sent = await self._sock.sendall(data)
        return sent

    async def recv_response(self):
        while True:
            data = await self._sock.recv(self._max_recv)
            if not data:
                raise ConnectionClosedError("connection closed by peer")
            self._reader.feed(data)
            res = self._reader.gets()
            if res is False:  # don't want to ignore None
                continue
            return res
