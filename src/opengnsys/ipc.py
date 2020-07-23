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


import json
import queue
import socket
import threading
import traceback

from opengnsys.utils import toUnicode
from opengnsys.log import logger

# The IPC Server will wait for connections from clients
# Clients will open socket, and wait for data from server
# The messages sent (from server) will be the following (subject to future changes):
#     Message_id     Data               Action
#    ------------  --------         --------------------------
#    MSG_LOGOFF     None            Logout user from session
#    MSG_MESSAGE    message,level   Display a message with level (INFO, WARN, ERROR, FATAL)     # TODO: Include level, right now only has message
#    MSG_POPUP      title,message   Display a popup box with a title
#    MSG_SCRIPT     python script   Execute an specific python script INSIDE CLIENT environment (this messages is not sent right now)
# The messages received (sent from client) will be the following:
#     Message_id       Data               Action
#    ------------    --------         --------------------------
#    REQ_LOGOUT                   Logout user from session
#    REQ_INFORMATION  None            Request information from ipc server (maybe configuration parameters in a near future)
#    REQ_LOGIN        python script   Execute an specific python script INSIDE CLIENT environment (this messages is not sent right now)
#
# All messages are in the form:
# BYTE
#  0           1-2                        3 4 ...
# MSG_ID   DATA_LENGTH (little endian)    Data (can be 0 length)
# With a previous "MAGIC" header in front of each message

# Client messages
MSG_LOGOFF = 0xA1  # Request log off from an user
MSG_MESSAGE = 0xB2
MSG_POPUP = 0xB3
MSG_SCRIPT = 0xC3

# Request messages
REQ_MESSAGE = 0xD4
REQ_POPUP = 0xD5
REQ_LOGIN = 0xE5
REQ_LOGOUT = 0xF6

# Reverse msgs dict for debugging
REV_DICT = {
    MSG_LOGOFF: 'MSG_LOGOFF',
    MSG_MESSAGE: 'MSG_MESSAGE',
    MSG_POPUP: 'MSG_POPUP',
    MSG_SCRIPT: 'MSG_SCRIPT',
    REQ_LOGIN: 'REQ_LOGIN',
    REQ_LOGOUT: 'REQ_LOGOUT',
    REQ_MESSAGE: 'REQ_MESSAGE'
}

MAGIC = b'\x4F\x47\x41\x00'  # OGA in hex with a padded 0 to the right


# States for client processor
ST_SECOND_BYTE = 0x01
ST_RECEIVING = 0x02
ST_PROCESS_MESSAGE = 0x02


class ClientProcessor(threading.Thread):
    def __init__(self, parent, clientSocket):
        super(self.__class__, self).__init__()
        self.parent = parent
        self.clientSocket = clientSocket
        self.running = False
        self.messages = queue.Queue(32)

    def stop(self):
        logger.debug('Stopping client processor')
        self.running = False

    def processRequest(self, msg, data):
        logger.debug('Got Client message {}={}'.format(msg, REV_DICT.get(msg)))
        if self.parent.clientMessageProcessor is not None:
            self.parent.clientMessageProcessor(msg, data)

    def run(self):
        self.running = True
        self.clientSocket.setblocking(0)

        state = None
        recv_msg = None
        recv_data = None
        msg_len = 0
        while self.running:
            try:
                counter = 1024
                while counter > 0:  # So we process at least the incoming queue every XX bytes readed
                    counter -= 1
                    b = self.clientSocket.recv(1)
                    if b == b'':
                        # Client disconnected
                        self.running = False
                        break
                    buf = int.from_bytes(b, 'big')  # Empty buffer, this is set as non-blocking
                    if state is None:
                        if buf in (REQ_MESSAGE, REQ_LOGIN, REQ_LOGOUT):
                            logger.debug('State set to {}'.format(buf))
                            state = buf
                            recv_msg = buf
                            continue  # Get next byte
                        else:
                            logger.debug('Got unexpected data {}'.format(buf))
                    elif state in (REQ_MESSAGE, REQ_LOGIN, REQ_LOGOUT):
                        logger.debug('First length byte is {}'.format(buf))
                        msg_len = buf
                        state = ST_SECOND_BYTE
                        continue
                    elif state == ST_SECOND_BYTE:
                        msg_len += buf << 8
                        logger.debug('Second length byte is {}, len is {}'.format(buf, msg_len))
                        if msg_len == 0:
                            self.processRequest(recv_msg, None)
                            state = None
                            break
                        state = ST_RECEIVING
                        recv_data = b''
                        continue
                    elif state == ST_RECEIVING:
                        recv_data += bytes([buf])
                        msg_len -= 1
                        if msg_len == 0:
                            self.processRequest(recv_msg, recv_data)
                            recv_data = None
                            state = None
                            break
                    else:
                        logger.debug('Got invalid message from request: {}, state: {}'.format(buf, state))
            except socket.error as e:
                # If no data is present, no problem at all, pass to check messages
                pass
            except Exception as e:
                tb = traceback.format_exc()
                logger.error('Error: {}, trace: {}'.format(e, tb))

            if self.running is False:
                break

            try:
                msg = self.messages.get(block=True, timeout=1)
            except queue.Empty:  # No message got in time @UndefinedVariable
                continue

            logger.debug('Got message {}={}'.format(msg, REV_DICT.get(msg[0])))

            try:
                m = msg[1] if msg[1] is not None else b''
                l = len(m)
                data = MAGIC + bytes([msg[0]]) + bytes([l & 0xFF]) + bytes([l >> 8]) + m
                try:
                    self.clientSocket.sendall(data)
                except socket.error as e:
                    # Send data error
                    logger.debug('Socket connection is no more available: {}'.format(e.args))
                    self.running = False
            except Exception as e:
                logger.error('Invalid message in queue: {}'.format(e))

        logger.debug('Client processor stopped')
        try:
            self.clientSocket.close()
        except Exception:
            pass  # If can't close, nothing happens, just end thread


class ServerIPC(threading.Thread):

    def __init__(self, listenPort, clientMessageProcessor=None):
        super(self.__class__, self).__init__()
        self.port = listenPort
        self.running = False
        self.serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.threads = []
        self.clientMessageProcessor = clientMessageProcessor

    def stop(self):
        logger.debug('Stopping Server IPC')
        self.running = False
        for t in self.threads:
            t.stop()
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(('localhost', self.port))
        self.serverSocket.close()

        for t in self.threads:
            t.join()

    def sendMessage(self, msg_id, msg_data):
        """
        Notify message to all listening threads
        """
        logger.debug('Sending message {}({}),{} to all clients'.format(msg_id, REV_DICT.get(msg_id), msg_data))

        # Convert to bytes so length is correctly calculated
        if isinstance(msg_data, str):
            msg_data = str.encode(msg_data)

        for t in self.threads:
            if t.isAlive():
                logger.debug('Sending to {}'.format(t))
                t.messages.put((msg_id, msg_data))

    def sendLoggofMessage(self):
        self.sendMessage(MSG_LOGOFF, '')

    def sendMessageMessage(self, message):
        self.sendMessage(MSG_MESSAGE, message)

    def sendPopupMessage(self, title, message):
        self.sendMessage(MSG_POPUP, {'title': title, 'message': message})

    def sendScriptMessage(self, script):
        self.sendMessage(MSG_SCRIPT, script)

    def cleanupFinishedThreads(self):
        """
        Cleans up current threads list
        """
        aliveThreads = []
        for t in self.threads:
            if t.isAlive():
                logger.debug('Thread {} is alive'.format(t))
                aliveThreads.append(t)
        self.threads[:] = aliveThreads

    def run(self):
        self.running = True

        self.serverSocket.bind(('localhost', self.port))
        self.serverSocket.setblocking(True)
        self.serverSocket.listen(4)

        while True:
            try:
                (clientSocket, address) = self.serverSocket.accept()
                # Stop processing if thread is mean to stop
                if self.running is False:
                    break
                logger.debug('Got connection from {}'.format(address))

                self.cleanupFinishedThreads()  # House keeping

                logger.debug('Starting new thread, current: {}'.format(self.threads))
                t = ClientProcessor(self, clientSocket)
                self.threads.append(t)
                t.start()
            except Exception as e:
                logger.error('Got an exception on Server ipc thread: {}'.format(e))


class ClientIPC(threading.Thread):
    def __init__(self, listenPort):
        super(ClientIPC, self).__init__()
        self.port = listenPort
        self.running = False
        self.clientSocket = None
        self.messages = queue.Queue(32)  # @UndefinedVariable

        self.connect()

    def stop(self):
        self.running = False

    def getMessage(self):
        while self.running:
            try:
                return self.messages.get(timeout=1)
            except queue.Empty:
                continue

        return None

    def sendRequestMessage(self, msg, data=None):
        logger.debug('Sending request for msg: {}({}), {}'.format(msg, REV_DICT.get(msg), data))
        if data is None:
            data = b''

        if isinstance(data, str):
            data = str.encode(data)

        l = len(data)
        msg = bytes([msg]) + bytes([l & 0xFF]) + bytes([l >> 8]) + data
        self.clientSocket.sendall(msg)

    def sendLogin(self, user_data):
        self.sendRequestMessage(REQ_LOGIN, ','.join(user_data))

    def sendLogout(self, username):
        self.sendRequestMessage(REQ_LOGOUT, username)

    def sendMessage(self, module, message, data=None):
        """
        Sends a message "message" with data (data will be encoded as json, so ensure that it is serializable)
        @param module: Module that will receive this message
        @param message: Message to send. This message is "customized", and understand by modules
        @param data: Data to be send as message companion
        """
        msg = '\0'.join((module, message, json.dumps(data)))
        self.sendRequestMessage(REQ_MESSAGE, msg)

    def messageReceived(self):
        """
        Override this method to automatically get notified on new message
        received. Message is at self.messages queue
        """
        pass

    def receiveBytes(self, number):
        msg = b''
        while self.running and len(msg) < number:
            try:
                buf = self.clientSocket.recv(number - len(msg))
                if buf == b'':
                    logger.debug('Buf {}, msg {}({})'.format(buf, msg, REV_DICT.get(msg)))
                    self.running = False
                    break
                msg += buf
            except socket.timeout:
                pass

        if self.running is False:
            logger.debug('Not running, returning None')
            return None
        return msg

    def connect(self):
        self.clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.clientSocket.connect(('localhost', self.port))
        self.clientSocket.settimeout(2)  # Static, custom socket timeout of 2 seconds for local connection (no network)

    def run(self):
        self.running = True

        while self.running:
            try:
                msg = b''
                # We look for magic message header
                while self.running:  # Wait for MAGIC
                    try:
                        buf = self.clientSocket.recv(len(MAGIC) - len(msg))
                        if buf == b'':
                            self.running = False
                            break
                        msg += buf
                        if len(msg) != len(MAGIC):
                            continue  # Do not have message
                        if msg != MAGIC:  # Skip first byte an continue searchong
                            msg = msg[1:]
                            continue
                        break
                    except socket.timeout:  # Timeout is here so we can get stop thread
                        continue

                if self.running is False:
                    break

                # Now we get message basic data (msg + datalen)
                msg = bytearray(self.receiveBytes(3))

                # We have the magic header, here comes the message itself
                if msg is None:
                    continue

                msgId = msg[0]
                dataLen = msg[1] + (msg[2] << 8)
                if msgId not in (MSG_LOGOFF, MSG_MESSAGE, MSG_SCRIPT):
                    raise Exception('Invalid message id: {}'.format(msgId))

                data = self.receiveBytes(dataLen)
                if data is None:
                    continue

                self.messages.put((msgId, data))
                self.messageReceived()

            except socket.error as e:
                logger.error('Communication with server got an error: {}'.format(toUnicode(e.strerror)))
                self.running = False
                return
            except Exception as e:
                tb = traceback.format_exc()
                logger.error('Error: {}, trace: {}'.format(e, tb))

        try:
            self.clientSocket.close()
        except Exception:
            pass  # If can't close, nothing happens, just end thread
