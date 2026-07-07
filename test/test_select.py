#
# This file is part of python-tdbus. Python-tdbus is free software
# available under the terms of the MIT license. See the file "LICENSE" that
# was provided together with this source file for the licensing terms.
#
# Copyright (c) 2012 the python-tdbus authors. See the file "AUTHORS" for a
# complete list.

import threading
import unittest

from tdbus import _tdbus, DBUS_BUS_SESSION, SimpleDBusConnection, \
    DBusHandler, method, signal_handler
from .base import BaseTest


IFACE_EXAMPLE = 'com.example'


class TestFlushWithQueuedMessages(unittest.TestCase, BaseTest):
    """Regression test: flush() releases the GIL and libdbus toggles the
    write watch from inside dbus_connection_flush(), invoking a Python
    callback. This used to segfault because the callback ran without a
    Python thread state."""

    def test_flush_queued_signals(self):
        conn = SimpleDBusConnection(DBUS_BUS_SESSION)
        # queue enough outgoing data that the socket buffer fills up and
        # flush() has actual work (and watch toggling) left to do
        for i in range(200):
            conn.send_signal('/', 'Spam', IFACE_EXAMPLE,
                             format='s', args=['x' * 4096])
        conn._connection.flush()
        conn.close()


class EchoHandler(DBusHandler):

    def __init__(self):
        super(EchoHandler, self).__init__()
        self.received = threading.Event()

    @method(interface=IFACE_EXAMPLE, member='Echo')
    def echo(self, message):
        self.set_response(message.get_signature(), message.get_args())

    @signal_handler(interface=IFACE_EXAMPLE, member='Ping')
    def ping(self, message):
        self.received.set()

    @method(interface=IFACE_EXAMPLE, member='Stop')
    def stop(self, _):
        self.connection.stop()


class TestSimpleDispatch(unittest.TestCase, BaseTest):
    """Method calls and signals over SimpleDBusConnection."""

    @classmethod
    def setUpClass(cls):
        super(TestSimpleDispatch, cls).setUpClass()
        cls.handler = EchoHandler()
        cls.server = SimpleDBusConnection(DBUS_BUS_SESSION)
        cls.server.add_handler(cls.handler)
        cls.server_name = cls.server.get_unique_name()
        cls.server_thread = threading.Thread(target=cls.server.dispatch)
        cls.server_thread.start()
        cls.client = SimpleDBusConnection(DBUS_BUS_SESSION)

    @classmethod
    def tearDownClass(cls):
        cls.client.call_method('/', 'Stop', IFACE_EXAMPLE,
                               destination=cls.server_name)
        cls.server_thread.join()
        cls.client.close()
        cls.server.close()
        super(TestSimpleDispatch, cls).tearDownClass()

    def test_blocking_method_call(self):
        reply = self.client.call_method('/', 'Echo', IFACE_EXAMPLE, 'si',
                                        ['hello', 42],
                                        destination=self.server_name,
                                        timeout=10)
        self.assertEqual(reply.get_args(), ('hello', 42))

    def test_signal_roundtrip(self):
        self.handler.received.clear()
        self.client.send_signal('/', 'Ping', IFACE_EXAMPLE,
                                destination=self.server_name)
        self.client._connection.flush()
        self.assertTrue(self.handler.received.wait(10))

    def test_concurrent_method_calls(self):
        errors = []

        def worker():
            try:
                for i in range(10):
                    reply = self.client.call_method(
                        '/', 'Echo', IFACE_EXAMPLE, 'i', [i],
                        destination=self.server_name, timeout=10)
                    if reply.get_args() != (i,):
                        errors.append(reply.get_args())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


class TestBusMethods(unittest.TestCase, BaseTest):
    """Calls against the message bus itself."""

    @classmethod
    def setUpClass(cls):
        super(TestBusMethods, cls).setUpClass()
        cls.conn = SimpleDBusConnection(DBUS_BUS_SESSION)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        super(TestBusMethods, cls).tearDownClass()

    def test_list_names(self):
        reply = self.conn.call_method(_tdbus.DBUS_PATH_DBUS, 'ListNames',
                                      _tdbus.DBUS_INTERFACE_DBUS,
                                      destination=_tdbus.DBUS_SERVICE_DBUS,
                                      timeout=10)
        names = reply.get_args()[0]
        self.assertIn(self.conn.get_unique_name(), names)

    def test_register_name(self):
        reply = self.conn.register_name('org.tdbus.TestSelect')
        self.assertEqual(reply, _tdbus.DBUS_REQUEST_NAME_REPLY_PRIMARY_OWNER)

    def test_concurrent_calls_from_threads(self):
        errors = []

        def worker():
            try:
                for _ in range(10):
                    reply = self.conn.call_method(
                        _tdbus.DBUS_PATH_DBUS, 'GetId',
                        _tdbus.DBUS_INTERFACE_DBUS,
                        destination=_tdbus.DBUS_SERVICE_DBUS, timeout=10)
                    reply.get_args()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
