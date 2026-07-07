"""
This file is part of python-tdbus. Python-tdbus is free software
available under the terms of the MIT license. See the file "LICENSE" that
was provided together with this source file for the licensing terms.

Copyright (c) 2012 the python-tdbus authors. See the file "AUTHORS" for a
complete list.
"""
import gc
import unittest
import weakref

from tdbus import SimpleDBusConnection, DBUS_BUS_SESSION
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

    def test_connection_collected_without_close(self):
        conn = SimpleDBusConnection(DBUS_BUS_SESSION)
        ref = weakref.ref(conn._connection.get_loop())
        del conn
        gc.collect()
        self.assertIsNone(ref())

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
