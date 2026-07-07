#
# This file is part of python-tdbus. Python-tdbus is free software
# available under the terms of the MIT license. See the file "LICENSE" that
# was provided together with this source file for the licensing terms.
#
# Copyright (c) 2012 the python-tdbus authors. See the file "AUTHORS" for a
# complete list.

import os
import re
import signal
import subprocess
import unittest

import tdbus


class BaseTest(object):
    """Test infrastructure for tdbus tests."""

    _re_assign = re.compile(r'^([a-zA-Z_][a-zA-Z0-9_]*)=' \
                            r'''([^"']*?|'[^']*'|"([^"\\]|\\.)*");?$''')

    @classmethod
    def setUpClass(cls):
        cls._have_session_bus = False
        try:
            output = subprocess.check_output(['dbus-launch', '--sh-syntax'],
                                             text=True)
        except OSError:
            raise unittest.SkipTest('dbus-launch is required for running this test')
        for line in output.splitlines():
            mobj = cls._re_assign.match(line)
            if not mobj:
                continue
            key = mobj.group(1)
            value = mobj.group(2)
            if value.startswith('"') or value.startswith("'"):
                value = value[1:-1]
            if key == 'DBUS_SESSION_BUS_ADDRESS':
                cls._bus_address = value
                # the following is a trick to allow us to have a different
                # session bus for each test.
                tdbus.DBUS_BUS_SESSION = value
                # test modules import DBUS_BUS_SESSION ("<SESSION>") by value
                # at import time; the environment variable is what makes
                # libdbus resolve "<SESSION>" to the bus launched above.
                os.environ['DBUS_SESSION_BUS_ADDRESS'] = value
            elif key == 'DBUS_SESSION_BUS_PID':
                cls._bus_pid = int(value)
        cls._have_session_bus = True

    @classmethod
    def tearDownClass(cls):
        if not cls._have_session_bus:
            return
        os.kill(cls._bus_pid, signal.SIGTERM)
