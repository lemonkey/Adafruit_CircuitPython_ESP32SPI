# The MIT License (MIT)
#
# Copyright (c) 2019 ladyada for Adafruit Industries
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""
`adafruit_esp32spi_socket`
================================================================================

A socket compatible interface thru the ESP SPI command set

* Author(s): ladyada
"""


import time
import gc
from micropython import const

_the_interface = None   # pylint: disable=invalid-name
def set_interface(iface):
    """Helper to set the global internet interface"""
    global _the_interface   # pylint: disable=global-statement, invalid-name
    _the_interface = iface

SOCK_STREAM = const(1)
AF_INET = const(2)

MAX_PACKET = const(4000)

# pylint: disable=too-many-arguments, unused-argument
def getaddrinfo(host, port, family=0, socktype=0, proto=0, flags=0):
    """Given a hostname and a port name, return a 'socket.getaddrinfo'
    compatible list of tuples. Honestly, we ignore anything but host & port"""
    if not isinstance(port, int):
        raise RuntimeError("Port must be an integer")
    ipaddr = _the_interface.get_host_by_name(host)
    return [(AF_INET, socktype, proto, '', (ipaddr, port))]
# pylint: enable=too-many-arguments, unused-argument

# pylint: disable=unused-argument, redefined-builtin, invalid-name
class socket:
    """A simplified implementation of the Python 'socket' class, for connecting
    through an interface to a remote device"""
    def __init__(self, family=AF_INET, type=SOCK_STREAM, proto=0, fileno=None):
        if family != AF_INET:
            raise RuntimeError("Only AF_INET family supported")
        if type != SOCK_STREAM:
            raise RuntimeError("Only SOCK_STREAM type supported")
        self._buffer = b''
        self._socknum = _the_interface.get_socket()
        self.settimeout(0)
        print("socket created")

    def connect(self, address, conntype=None):
        """Connect the socket to the 'address' (which can be 32bit packed IP or
        a hostname string). 'conntype' is an extra that may indicate SSL or not,
        depending on the underlying interface"""
        print("connecting...")
        host, port = address
        if conntype is None:
            conntype = _the_interface.TCP_MODE
        if not _the_interface.socket_connect(self._socknum, host, port, conn_mode=conntype):
            raise RuntimeError("Failed to connect to host", host)
        self._buffer = b''

    def write(self, data):         # pylint: disable=no-self-use
        """Send some data to the socket"""
        _the_interface.socket_write(self._socknum, data)
        gc.collect()

    def readline(self):
        """Attempt to return as many bytes as we can up to but not including '\r\n'"""
        # print("Socket readline")
        stamp = time.monotonic()
        # print("buffer: ", self._buffer)
        while b'\r\n' not in self._buffer:
            # there's no line already in there, read some more
            avail = min(_the_interface.socket_available(self._socknum), MAX_PACKET)
            if avail != 0:
                print("avail: ", avail)
            if avail:
                self._buffer += _the_interface.socket_read(self._socknum, avail)
            elif self._timeout > 0 and time.monotonic() - stamp > self._timeout:
                self.close()  # Make sure to close socket so that we don't exhaust sockets.
                raise RuntimeError("Didn't receive full response, failing out")
        firstline, self._buffer = self._buffer.split(b'\r\n', 1)
        gc.collect()
        return firstline

    def read(self, size=0):
        """Read up to 'size' bytes from the socket, this may be buffered internally!
        If 'size' isnt specified, return everything in the buffer."""
        # print("Socket read: ", size)
        if size == 0:   # read as much as we can at the moment
            while True:
                avail = min(_the_interface.socket_available(self._socknum), MAX_PACKET)
                if avail:
                    self._buffer += _the_interface.socket_read(self._socknum, avail)
                else:
                    break
            gc.collect()
            ret = self._buffer
            self._buffer = b''
            gc.collect()
            return ret
        stamp = time.monotonic()

        to_read = size - len(self._buffer)

        # print("size: ", size)
        # print("buffer length: ", len(self._buffer))

        # if this is too short, could end too early and size of file written will not match
        # the content-length from server...
        #
        # read_timeout = 1
        # read_timeout = self._timeout
        read_timeout = 8

        received = []
        while to_read > 0:
            # print("Bytes to read:", to_read)
            available_bytes = _the_interface.socket_available(self._socknum)
            
            # if available_bytes > 0:
            #     print("available bytes on sock: ", available_bytes)

            # if available_bytes > MAX_PACKET:
            #     print("Warning: available bytes is > MAX_PACKET: ", MAX_PACKET)

            avail = min(available_bytes, MAX_PACKET)
            
            if avail:
                # print("avail: ", avail)
                stamp = time.monotonic()
                recv = _the_interface.socket_read(self._socknum, min(to_read, avail))
                received.append(recv)
                to_read -= len(recv)
                gc.collect()
            # else:
            #     print("nothing left to read! waiting to timeout... ", (time.monotonic() - stamp))
            #if self._timeout > 0 and time.monotonic() - stamp > self._timeout:
            if read_timeout > 0 and time.monotonic() - stamp > read_timeout:
                #print("socket.read timeout ", self._timeout)
                print("socket.read timeout ", read_timeout)
                break
        #print(received)
        self._buffer += b''.join(received)

        # print("len(self._buffer) ", len(self._buffer))

        ret = None
        if len(self._buffer) == size:
            ret = self._buffer
            self._buffer = b''
        else:
            ret = self._buffer[:size]
            self._buffer = self._buffer[size:]

        # print("size: ", size)
        # print("len(ret) ", len(ret))

        gc.collect()
        return ret

    def settimeout(self, value):
        """Set the read timeout for sockets, if value is 0 it will block"""
        print("setting timeout: ", value)
        self._timeout = value

    def close(self):
        """Close the socket, after reading whatever remains"""
        _the_interface.socket_close(self._socknum)
# pylint: enable=unused-argument, redefined-builtin, invalid-name
