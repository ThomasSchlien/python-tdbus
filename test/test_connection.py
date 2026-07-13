"""
This file is part of python-tdbus. Python-tdbus is free software
available under the terms of the MIT license. See the file "LICENSE" that
was provided together with this source file for the licensing terms.

Copyright (c) 2012 the python-tdbus authors. See the file "AUTHORS" for a
complete list.
"""
import gc
import os
import unittest
import weakref

from tdbus import _tdbus, SimpleDBusConnection, DBUS_BUS_SESSION
from .base import BaseTest

try:
    import gevent
    from tdbus import GEventDBusConnection
except ImportError:
    gevent = None
    GEventDBusConnection = None


class TestSimpleDBusConnection(unittest.TestCase, BaseTest):
    """Test suite for D-BUS connection."""

    def test_connection_open(self):
        conn = SimpleDBusConnection(DBUS_BUS_SESSION)
        conn.open(DBUS_BUS_SESSION)
        conn.close()

    def test_connection_init(self):
        conn = SimpleDBusConnection(DBUS_BUS_SESSION)
        conn.close()

    def test_connection_multiple_open(self):
        conn = SimpleDBusConnection(DBUS_BUS_SESSION)
        conn.close()
        conn.open(DBUS_BUS_SESSION)
        conn.close()

    def test_get_unique_name(self):
        conn = SimpleDBusConnection(DBUS_BUS_SESSION)
        name = conn.get_unique_name()
        assert name.startswith(':')
        conn.close()

    def test_connection_collected_after_close(self):
        # The connection and its loop form a reference cycle; the C
        # Connection type supports cyclic GC so it must be reclaimed.
        conn = SimpleDBusConnection(DBUS_BUS_SESSION)
        ref = weakref.ref(conn._connection.get_loop())
        conn.close()
        del conn
        gc.collect()
        self.assertIsNone(ref())

    @unittest.skipUnless(os.path.isdir('/proc/self/fd'),
                         'requires /proc file descriptor listing')
    def test_connection_reinit_does_not_leak(self):
        # __init__ called a second time must close the previous libdbus
        # connection instead of leaking it and its file descriptor.
        conn = _tdbus.Connection(DBUS_BUS_SESSION)
        numfds = len(os.listdir('/proc/self/fd'))
        for _ in range(4):
            conn.__init__(DBUS_BUS_SESSION)
        self.assertEqual(len(os.listdir('/proc/self/fd')), numfds)
        # the connection swapped in last must be usable
        self.assertTrue(conn.get_unique_name().startswith(':'))
        conn.close()

    def test_connection_collected_without_close(self):
        conn = SimpleDBusConnection(DBUS_BUS_SESSION)
        ref = weakref.ref(conn._connection.get_loop())
        del conn
        gc.collect()
        self.assertIsNone(ref())

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires os.fork')
    def test_use_after_fork_raises(self):
        # libdbus connections cannot be used across fork(); using one in
        # the child must raise instead of silently hanging.
        conn = SimpleDBusConnection(DBUS_BUS_SESSION)
        pid = os.fork()
        if pid == 0:
            # child: report the outcome through the exit status
            try:
                conn.call_method('/org/freedesktop/DBus', 'GetId',
                                 'org.freedesktop.DBus',
                                 destination='org.freedesktop.DBus',
                                 timeout=1)
            except RuntimeError:
                os._exit(0)
            except BaseException:
                os._exit(2)
            os._exit(1)
        _, status = os.waitpid(pid, 0)
        self.assertTrue(os.WIFEXITED(status))
        self.assertEqual(os.WEXITSTATUS(status), 0)
        # the parent's connection must remain usable
        reply = conn.call_method('/org/freedesktop/DBus', 'GetId',
                                 'org.freedesktop.DBus',
                                 destination='org.freedesktop.DBus',
                                 timeout=5)
        self.assertTrue(reply.get_args())
        conn.close()

@unittest.skipIf(gevent is None, 'gevent is not available')
class TestGeventDBusConnection(unittest.TestCase, BaseTest):
    """Test suite for D-BUS connection."""

    def test_connection_open(self):
        conn = GEventDBusConnection(DBUS_BUS_SESSION)
        conn.open(DBUS_BUS_SESSION)
        conn.close()

    def test_connection_init(self):
        conn = GEventDBusConnection(DBUS_BUS_SESSION)
        conn.close()

    def test_connection_multiple_open(self):
        conn = GEventDBusConnection(DBUS_BUS_SESSION)
        conn.close()
        conn.open(DBUS_BUS_SESSION)
        conn.close()

    def test_get_unique_name(self):
        conn = GEventDBusConnection(DBUS_BUS_SESSION)
        name = conn.get_unique_name()
        assert name.startswith(':')
        conn.close()

    def test_timeout_toggled_interval_change(self):
        # timeout_toggled() with a changed interval used to create the new
        # timer with the old interval and store a bare event where every
        # other path expects an (interval, event) tuple, crashing the next
        # remove_timeout()/timeout_toggled().
        from tdbus.gevent import GEventLoop

        class FakeTimeout(object):
            def __init__(self, interval):
                self.interval = interval
                self.enabled = True
                self.data = None
            def get_interval(self):
                return self.interval
            def get_enabled(self):
                return self.enabled
            def set_data(self, data):
                self.data = data
            def get_data(self):
                return self.data

        loop = GEventLoop(None)
        timeout = FakeTimeout(1000)
        loop.add_timeout(timeout)
        interval, event = timeout.get_data()
        self.assertEqual(interval, 1000)
        # disable, then re-enable with a changed interval (the sequence
        # libdbus uses when it adjusts a timeout)
        timeout.enabled = False
        loop.timeout_toggled(timeout)
        timeout.interval = 2000
        timeout.enabled = True
        loop.timeout_toggled(timeout)
        new_interval, new_event = timeout.get_data()
        self.assertEqual(new_interval, 2000)
        self.assertIsNot(new_event, event)
        # remove_timeout() must be able to unpack the stored data
        loop.remove_timeout(timeout)
        self.assertIsNone(timeout.get_data())
