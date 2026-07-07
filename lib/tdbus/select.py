#
# This file is part of python-tdbus. Python-tdbus is free software
# available under the terms of the MIT license. See the file "LICENSE" that
# was provided together with this source file for the licensing terms.
#
# Copyright (c) 2012 the python-tdbus authors. See the file "AUTHORS" for a
# complete list.

from __future__ import division, absolute_import

import errno
import heapq
import itertools
import select
import time
from threading import RLock

from tdbus import _tdbus
from tdbus.connection import DBusConnection, DBusError
from tdbus.loop import EventLoop


class SelectLoop(EventLoop):
    """This is a very simple event loop based on select().

    This is only useful if you don't already have an event loop
    in your application architecture, and either want to use blocking
    calls or make D-BUS your main event loop.

    This loop is portable. It is also inefficient when compared to
    other even loops because of its use of select() (although it should
    be fine for most use cases).
    """

    def __init__(self, connection):
        self._connection = connection
        self.watches = []
        self.timeouts = []
        # tiebreaker for heap entries with equal expiry times; Timeout
        # objects themselves are not orderable
        self._counter = itertools.count()

    def add_watch(self, watch):
        self.watches.append(watch)

    def remove_watch(self, watch):
        self.watches.remove(watch)

    def watch_toggled(self, watch):
        pass

    def add_timeout(self, timeout):
        expires = time.monotonic() + timeout.get_interval() / 1000
        heapq.heappush(self.timeouts, (expires, next(self._counter), timeout))

    def remove_timeout(self, timeout):
        for i in range(len(self.timeouts)):
            if self.timeouts[i][2] is timeout:
                del self.timeouts[i]
                heapq.heapify(self.timeouts)
                break

    def timeout_toggled(self, timeout):
        pass


class SimpleDBusConnection(DBusConnection):
    """A connection that uses a simple select() based event loop.

    This class can be used as a standalone connection in case your
    application does not have an event loop. Calls to call_method()
    will block until a response is received.
    """

    Loop = SelectLoop
    Local = type('Object', (object,), {})

    def __init__(self, address):
        super(SimpleDBusConnection, self).__init__(address)
        # Serializes blocking method calls from multiple threads. An RLock
        # so that a handler invoked during dispatch() may itself issue a
        # nested call_method() without deadlocking.
        self.mutex = RLock()

    def call_method(self, *args, **kwargs):
        with self.mutex:
            callback = kwargs.get('callback')
            if callback is not None:
                super(SimpleDBusConnection, self).call_method(*args, **kwargs)
                return
            replies = []
            def _method_callback(message):
                replies.append(message)
                self.stop()
            kwargs['callback'] = _method_callback
            super(SimpleDBusConnection, self).call_method(*args, **kwargs)
            # A nested call_method() from a handler stops the loop early, so
            # keep dispatching until our own reply has arrived.
            while not replies:
                self.dispatch()
            reply = replies[0]
            self._handle_errors(reply)
            return reply

    def dispatch(self):
        """Start the loop."""
        self._stop = False
        loop = self._connection.get_loop()
        while not self._stop:
            rfds = []; wfds = []
            for watch in loop.watches:
                if not watch.get_enabled():
                    continue
                fd = watch.get_fd()
                flags = watch.get_flags()
                if flags & _tdbus.DBUS_WATCH_READABLE:
                    rfds.append(fd)
                if flags & _tdbus.DBUS_WATCH_WRITABLE:
                    wfds.append(fd)
            if loop.timeouts:
                timeout = max(0, loop.timeouts[0][0] - time.monotonic())
            else:
                timeout = 4
            try:
                rfds, wfds, _ = select.select(rfds, wfds, [], timeout)
            except OSError as e:
                if e.errno != errno.EINTR:
                    raise
                rfds, wfds = [], []
            for watch in loop.watches:
                if not watch.get_enabled():
                    continue
                fd = watch.get_fd()
                flags = 0
                if fd in rfds:
                    flags |= _tdbus.DBUS_WATCH_READABLE
                if fd in wfds:
                    flags |= _tdbus.DBUS_WATCH_WRITABLE
                if flags:
                    watch.handle(flags)
            now = time.monotonic()
            while loop.timeouts and loop.timeouts[0][0] < now:
                expires, _, timeout = heapq.heappop(loop.timeouts)
                # re-arm before handling so that remove_timeout() calls made
                # from within handle() see (and can remove) this timeout
                heapq.heappush(loop.timeouts,
                               (expires + timeout.get_interval() / 1000,
                                next(loop._counter), timeout))
                timeout.handle()
            while self._connection.get_dispatch_status() == \
                        _tdbus.DBUS_DISPATCH_DATA_REMAINS:
                self._connection.dispatch()
        self._connection.flush()

    def stop(self):
        """Stop the event loop."""
        self._stop = True
