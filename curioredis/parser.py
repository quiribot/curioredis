# The MIT License (MIT)
#
# Copyright (c) 2014-2017 Alexey Popravka
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
from .errors import ProtocolError, ReplyError


class PyReader:
    """Pure-Python Redis protocol parser that follows hiredis.Reader
    interface (except setmaxbuf/getmaxbuf).
    """

    def __init__(self,
                 protocolError=ProtocolError,
                 replyError=ReplyError,
                 encoding=None):
        if not callable(protocolError):
            raise TypeError("Expected a callable")
        if not callable(replyError):
            raise TypeError("Expected a callable")
        self._parser = Parser(protocolError, replyError, encoding)

    def feed(self, data, o=0, l=-1):
        """Feed data to parser."""
        if l == -1:
            l = len(data) - o
        if o < 0 or l < 0:
            raise ValueError("negative input")
        if o + l > len(data):
            raise ValueError("input is larger than buffer size")
        print(f"o: {o}, l: {l}")
        self._parser.buf.extend(data[o:o + l])

    def gets(self):
        """Get parsed value or False otherwise.
        Error replies are return as replyError exceptions (not raised).
        Protocol errors are raised.
        """
        return self._parser.parse_one()

    def setmaxbuf(self, size):
        """No-op."""
        pass

    def getmaxbuf(self):
        """No-op."""
        return 0


class Parser:
    def __init__(self, protocolError, replyError, encoding):
        self.buf = bytearray()
        self.pos = 0
        self.protocolError = protocolError
        self.replyError = replyError
        self.encoding = encoding
        self._err = None
        self._gen = None

    def waitsome(self, size):
        # keep yielding false until at least `size` bytes added to buf.
        while len(self.buf) < self.pos + size:
            yield False

    def waitany(self):
        yield from self.waitsome(len(self.buf) + 1)

    def readone(self):
        if not self.buf[self.pos:1]:
            yield from self.waitany()
        val = self.buf[self.pos:1]
        self.pos += 1
        return val

    def readline(self, size=None):
        if size is not None:
            if len(self.buf) < size + 2 + self.pos:
                yield from self.waitsome(size + 2)
            offset = self.pos + size
            if self.buf[offset:offset + 2] != b'\r\n':
                raise self.error("Expected b'\r\n'")
        else:
            offset = self.buf.find(b'\r\n', self.pos)
            while offset < 0:
                yield from self.waitany()
                offset = self.buf.find(b'\r\n', self.pos)
        val = self.buf[self.pos:offset]
        self.pos = 0
        del self.buf[:offset + 2]
        return val

    def readint(self):
        try:
            return int((yield from self.readline()))
        except ValueError as exc:
            raise self.error(exc)

    def error(self, msg):
        self._err = self.protocolError(msg)
        return self._err

    def parse(self, is_bulk=False):
        if self._err is not None:
            raise self._err
        ctl = yield from self.readone()
        if ctl == b'+':
            val = yield from self.readline()
            if self.encoding is not None:
                try:
                    return val.decode(self.encoding)
                except UnicodeDecodeError:
                    pass
            return bytes(val)
        elif ctl == b'-':
            val = yield from self.readline()
            return self.replyError(val.decode('utf-8'))
        elif ctl == b':':
            return (yield from self.readint())
        elif ctl == b'$':
            val = yield from self.readint()
            if val == -1:
                return None
            val = yield from self.readline(val)
            if self.encoding:
                try:
                    return val.decode(self.encoding)
                except UnicodeDecodeError:
                    pass
            return bytes(val)
        elif ctl == b'*':
            val = yield from self.readint()
            if val == -1:
                return None
            bulk_array = []
            error = None
            for _ in range(val):
                try:
                    bulk_array.append((yield from self.parse(is_bulk=True)))
                except LookupError as err:
                    if error is None:
                        error = err
            if error is not None:
                raise error
            return bulk_array
        else:
            raise self.error("Invalid first byte: {!r}".format(ctl))

    def parse_one(self):
        if self._gen is None:
            self._gen = self.parse()
        try:
            self._gen.send(None)
        except StopIteration as exc:
            self._gen = None
            return exc.value
        except Exception:
            self._gen = None
            raise
        else:
            return False


try:
    import hiredis
    Reader = hiredis.Reader
except ImportError:
    Reader = PyReader
