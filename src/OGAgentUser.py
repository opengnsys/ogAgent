#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 Virtual Cable S.L.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright notice,
#      this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright notice,
#      this list of conditions and the following disclaimer in the documentation
#      and/or other materials provided with the distribution.
#    * Neither the name of Virtual Cable S.L. nor the names of its contributors
#      may be used to endorse or promote products derived from this software
#      without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
@author: Adolfo Gómez, dkmaster at dkmon dot com
"""
import atexit
import base64
import json
import sys
import time
from PyQt5 import QtCore, QtGui, QtWidgets

from about_dialog_ui import Ui_OGAAboutDialog
from message_dialog_ui import Ui_OGAMessageDialog
from opengnsys import VERSION, ipc, operations, utils
from opengnsys.config import readConfig
from opengnsys.loader import loadModules
from opengnsys.log import logger
from opengnsys.scriptThread import ScriptExecutorThread
from opengnsys.service import IPC_PORT

trayIcon = None


def sigAtExit():
    if trayIcon:
        trayIcon.quit()


# About dialog
class OGAAboutDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        QtWidgets.QDialog.__init__(self, parent)
        self.ui = Ui_OGAAboutDialog()
        self.ui.setupUi(self)
        self.ui.VersionLabel.setText("Version " + VERSION)

    def closeDialog(self):
        self.hide()


class OGAMessageDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        QtWidgets.QDialog.__init__(self, parent)
        self.ui = Ui_OGAMessageDialog()
        self.ui.setupUi(self)

    def message(self, message):
        self.ui.message.setText(message)
        self.show()

    def closeDialog(self):
        self.hide()


class MessagesProcessor(QtCore.QThread):
    logoff = QtCore.pyqtSignal(name='logoff')
    message = QtCore.pyqtSignal(tuple, name='message')
    script = QtCore.pyqtSignal(str, name='script')
    exit = QtCore.pyqtSignal(name='exit')

    def __init__(self, port):
        super(self.__class__, self).__init__()
        # Retries connection for a while
        for _ in range(10):
            try:
                self.ipc = ipc.ClientIPC(port)
                self.ipc.start()
                break
            except Exception:
                logger.debug('IPC Server is not reachable')
                self.ipc = None
                time.sleep(2)

        self.running = False

    def stop(self):
        self.running = False
        if self.ipc:
            self.ipc.stop()

    def isAlive(self):
        return self.ipc is not None

    def sendLogin(self, username, language):
        if self.ipc:
            self.ipc.sendLogin(username, language)

    def sendLogout(self, username):
        if self.ipc:
            self.ipc.sendLogout(username)

    def run(self):
        if self.ipc is None:
            return
        self.running = True

        # Wait a bit so we ensure IPC thread is running...
        time.sleep(2)

        while self.running and self.ipc.running:
            try:
                msg = self.ipc.getMessage()
                if msg is None:
                    break
                msg_id, data = msg
                logger.debug('Got Message on User Space: {}:{}'.format(msgId, data))
                if msg_id == ipc.MSG_MESSAGE:
                    module, message, data = data.split('\0')
                    self.message.emit((module, message, data))
                elif msg_id == ipc.MSG_LOGOFF:
                    self.logoff.emit()
                elif msg_id == ipc.MSG_SCRIPT:
                    self.script.emit(data.decode('utf-8'))
            except Exception as e:
                try:
                    logger.error('Got error on IPC thread {}'.format(utils.exceptionToMessage(e)))
                except:
                    logger.error('Got error on IPC thread (an unicode error??)')

        if self.ipc.running is False and self.running is True:
            logger.warn('Lost connection with Service, closing program')

        self.exit.emit()


class OGASystemTray(QtWidgets.QSystemTrayIcon):
    def __init__(self, app_, parent=None):
        self.app = app_
        self.config = readConfig(client=True)
        self.modules = None
        # Get opengnsys section as dict
        cfg = dict(self.config.items('opengnsys'))
        # Set up log level
        logger.setLevel(cfg.get('log', 'INFO'))

        self.ipcport = int(cfg.get('ipc_port', IPC_PORT))

        icon = QtGui.QIcon(':/images/img/oga.png')

        QtWidgets.QSystemTrayIcon.__init__(self, icon, parent)
        self.menu = QtWidgets.QMenu(parent)
        exit_action = self.menu.addAction("About")
        exit_action.triggered.connect(self.about)
        self.setContextMenu(self.menu)
        self.ipc = MessagesProcessor(self.ipcport)

        if self.ipc.isAlive() is False:
            raise Exception('No connection to service, exiting.')

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.timerFnc)

        self.stopped = False

        self.ipc.message.connect(self.message)
        self.ipc.exit.connect(self.quit)
        self.ipc.script.connect(self.executeScript)
        self.ipc.logoff.connect(self.logoff)

        self.aboutDlg = OGAAboutDialog()
        self.msgDlg = OGAMessageDialog()

        self.timer.start(1000)  # Launch idle checking every 1 seconds

        self.ipc.start()

    def initialize(self):
        # Load modules and activate them
        # Also, sends "login" event to service
        self.modules = loadModules(self, client=True)
        logger.debug('Modules: {}'.format(list(v.name for v in self.modules)))

        # Send init to all modules
        valid_mods = []
        for mod in self.modules:
            try:
                logger.debug('Activating module {}'.format(mod.name))
                mod.activate()
                valid_mods.append(mod)
            except Exception as e:
                logger.exception()
                logger.error("Activation of {} failed: {}".format(mod.name, utils.exceptionToMessage(e)))
        self.modules[:] = valid_mods  # copy instead of assignment
        # If this is running, it's because he have logged in, inform service of this fact
        self.ipc.sendLogin(operations.getCurrentUser(), operations.getSessionLanguage())

    def deinitialize(self):
        for mod in reversed(self.modules):  # Deinitialize reversed of initialization
            try:
                logger.debug('Deactivating module {}'.format(mod.name))
                mod.deactivate()
            except Exception as e:
                logger.exception()
                logger.error("Deactivation of {} failed: {}".format(mod.name, utils.exceptionToMessage(e)))

    def timerFnc(self):
        pass

    def message(self, msg):
        """
        Processes the message sent asynchronously, msg is an QString
        """
        try:
            logger.debug('msg: {}, {}'.format(type(msg), msg))
            module, message, data = msg
        except Exception as e:
            logger.error('Got exception {} processing message {}'.format(e, msg))
            return

        for v in self.modules:
            if v.name == module:  # Case Sensitive!!!!
                try:
                    logger.debug('Notifying message {} to module {} with json data {}'.format(message, v.name, data))
                    v.processMessage(message, json.loads(data))
                    return
                except Exception as e:
                    logger.error('Got exception {} processing generic message on {}'.format(e, v.name))

        logger.error('Module {} not found, messsage {} not sent'.format(module, message))

    def executeScript(self, script):
        logger.debug('Executing script')
        script = base64.b64decode(script.encode('ascii'))
        th = ScriptExecutorThread(script)
        th.start()

    def logoff(self):
        logger.debug('Logoff invoked')
        operations.logoff()  # Invoke log off

    def about(self):
        self.aboutDlg.exec_()

    def cleanup(self):
        logger.debug('Quit invoked')
        if self.stopped is False:
            self.stopped = True
            try:
                self.deinitialize()
            except Exception:
                logger.exception()
                logger.error('Got exception deinitializing modules')

            try:
                # If we close Client, send Logoff to Broker
                self.ipc.sendLogout(operations.getCurrentUser())
                time.sleep(1)
                self.timer.stop()
                self.ipc.stop()
            except Exception:
                # May we have lost connection with server, simply log and exit in that case
                logger.exception()
                logger.exception("Got an exception, processing quit")

            try:
                # operations.logoff()  # Uncomment this after testing to logoff user
                pass
            except Exception:
                pass

    def quit(self):
        # logger.debug("Exec quit {}".format(self.stopped))
        if self.stopped is False:
            self.cleanup()
            self.app.quit()

    def closeEvent(self, event):
        logger.debug("Exec closeEvent")
        event.accept()
        self.quit()


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)

    if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
        # QtGui.QMessageBox.critical(None, "Systray", "I couldn't detect any system tray on this system.")
        sys.exit(1)

    # This is important so our app won't close on messages windows (alerts, etc...)
    QtWidgets.QApplication.setQuitOnLastWindowClosed(False)

    try:
        trayIcon = OGASystemTray(app)
    except Exception as e:
        logger.exception()
        logger.error('OGA Service is not running, or it can\'t contact with OGA Server. User Tools stopped: {}'.format(
            utils.exceptionToMessage(e)))
        sys.exit(1)

    try:
        trayIcon.initialize()  # Initialize modules, etc..
    except Exception as e:
        logger.exception()
        logger.error('Exception initializing OpenGnsys User Agent {}'.format(utils.exceptionToMessage(e)))
        trayIcon.quit()
        sys.exit(1)

    app.aboutToQuit.connect(trayIcon.cleanup)
    trayIcon.show()

    # Catch kill and logout user :)
    atexit.register(sigAtExit)

    res = app.exec_()

    logger.debug('Exiting')
    trayIcon.quit()

    sys.exit(res)
