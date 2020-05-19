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
@author: Ramón M. Gómez, ramongomez at us dot es
"""


import os
import random
import shutil
import string
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from opengnsys import REST, operations, VERSION
from opengnsys.log import logger
from opengnsys.scriptThread import ScriptExecutorThread
from opengnsys.workers import ServerWorker


# Check authorization header decorator
def check_secret(fnc):
    """
    Decorator to check for received secret key and raise exception if it isn't valid.
    """
    def wrapper(*args, **kwargs):
        try:
            this, path, get_params, post_params, server = args  # @UnusedVariable
            # Accept "status" operation with no arguments or any function with Authorization header
            if fnc.__name__ == 'process_status' and not get_params:
                return fnc(*args, **kwargs)
            elif this.random == server.headers['Authorization']:
                return fnc(*args, **kwargs)
            else:
                raise Exception('Unauthorized operation')
        except Exception as e:
            logger.error(e)
            raise Exception(e)

    return wrapper


# Check if operation is permitted
def execution_level(level):
    def check_permitted(fnc):
        def wrapper(*args, **kwargs):
            levels = ['status', 'halt', 'full']
            this = args[0]
            try:
                if levels.index(level) <= levels.index(this.exec_level):
                    return fnc(*args, **kwargs)
                else:
                    raise Exception('Unauthorized operation')
            except Exception as e:
                logger.error(e)
                raise Exception(e)

        return wrapper

    return check_permitted


# Error handler decorator.
def catch_background_error(fnc):
    def wrapper(*args, **kwargs):
        this = args[0]
        try:
            fnc(*args, **kwargs)
        except Exception as e:
            this.REST.sendMessage('error?id={}'.format(kwargs.get('requestId', 'error')), {'error': '{}'.format(e)})
    return wrapper


class OpenGnSysWorker(ServerWorker):
    name = 'opengnsys'  # Module name
    interface = None  # Bound interface for OpenGnsys
    REST = None  # REST object
    user = []  # User sessions
    random = None  # Random string for secure connections
    length = 32  # Random string length
    exec_level = None  # Execution level (permitted operations)

    def onActivation(self):
        """
        Sends OGAgent activation notification to OpenGnsys server
        """
        t = 0
        # Generate random secret to send on activation
        self.random = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(self.length))
        # Ensure cfg has required configuration variables or an exception will be thrown
        url = self.service.config.get('opengnsys', 'remote')
        self.REST = REST(url)
        # Execution level ('full' by default)
        try:
            self.exec_level = self.service.config.get('opengnsys', 'level')
        except:
            self.exec_level = 'full'
        # Get network interfaces until they are active or timeout (5 minutes)
        for t in range(0, 300):
            try:
                self.interface = list(operations.getNetworkInfo())[0]  # Get first network interface
            except Exception as e:
                # Wait 1 sec. and retry
                time.sleep(1)
            finally:
                # Exit loop if interface is active
                if self.interface:
                    if t > 0:
                        logger.debug("Fetch connection data after {} tries".format(t))
                    break
        # Raise error after timeout
        if not self.interface:
            raise e
        # Loop to send initialization message
        for t in range(0, 100):
            try:
                try:
                    self.REST.sendMessage('ogagent/started', {'mac': self.interface.mac, 'ip': self.interface.ip,
                                                              'secret': self.random, 'ostype': operations.os_type,
                                                              'osversion': operations.os_version,
                                                              'agent_version': VERSION})
                    break
                except:
                    # Trying to initialize on alternative server, if defined
                    # (used in "exam mode" from the University of Seville)
                    self.REST = REST(self.service.config.get('opengnsys', 'altremote'))
                    self.REST.sendMessage('ogagent/started', {'mac': self.interface.mac, 'ip': self.interface.ip,
                                                              'secret': self.random, 'ostype': operations.os_type,
                                                              'osversion': operations.os_version, 'alt_url': True,
                                                              'agent_version': VERSION})
                    break
            except:
                time.sleep(3)
        # Raise error after timeout
        if 0 < t < 100:
            logger.debug('Successful connection after {} tries'.format(t))
        elif t == 100:
            raise Exception('Initialization error: Cannot connect to remote server')
        # Delete marking files
        for f in ['ogboot.me', 'ogboot.firstboot', 'ogboot.secondboot']:
            try:
                os.remove(os.sep + f)
            except OSError:
                pass
        # Copy file "HostsFile.FirstOctetOfIPAddress" to "HostsFile", if it exists
        # (used in "exam mode" from the University of Seville)
        hosts_file = os.path.join(operations.get_etc_path(), 'hosts')
        new_hosts_file = hosts_file + '.' + self.interface.ip.split('.')[0]
        if os.path.isfile(new_hosts_file):
            shutil.copyfile(new_hosts_file, hosts_file)

    def onDeactivation(self):
        """
        Sends OGAgent stopping notification to OpenGnsys server
        """
        logger.debug('onDeactivation')
        self.REST.sendMessage('ogagent/stopped', {'mac': self.interface.mac, 'ip': self.interface.ip,
                                                  'ostype': operations.os_type, 'osversion': operations.os_version})

    def processClientMessage(self, message, data):
        logger.debug('Got OpenGnsys message from client: {}, data {}'.format(message, data))

    def onLogin(self, data):
        """
        Sends session login notification to OpenGnsys server
        """
        user, sep, language = data.partition(',')
        logger.debug('Received login for {} with language {}'.format(user, language))
        self.user.append(user)
        self.REST.sendMessage('ogagent/loggedin', {'ip': self.interface.ip, 'user': user, 'language': language,
                                                   'ostype': operations.os_type, 'osversion': operations.os_version})

    def onLogout(self, user):
        """
        Sends session logout notification to OpenGnsys server
        """
        logger.debug('Received logout for {}'.format(user))
        try:
            self.user.pop()
        except IndexError:
            pass
        self.REST.sendMessage('ogagent/loggedout', {'ip': self.interface.ip, 'user': user})

    def process_ogclient(self, path, get_params, post_params, server):
        """
        This method can be overridden to provide your own message processor, or better you can
        implement a method that is called exactly as "process_" + path[0] (module name has been removed from path
        array) and this default processMessage will invoke it
        * Example:
            Imagine this invocation url (no matter if GET or POST): http://example.com:9999/Sample/mazinger/Z
            The HTTP Server will remove "Sample" from path, parse arguments and invoke this method as this:
            module.processMessage(["mazinger","Z"], get_params, post_params)

            This method will process "mazinger", and look for a "self" method that is called "process_mazinger",
            and invoke it this way:
               return self.process_mazinger(["Z"], get_params, post_params)

            In the case path is empty (that is, the path is composed only by the module name, like in
            "http://example.com/Sample", the "process" method will be invoked directly

            The methods must return data that can be serialized to json (i.e. Objects are not serializable to json,
            basic type are)
        """
        if not path:
            return "ok"
        try:
            operation = getattr(self, 'ogclient_' + path[0])
        except Exception:
            raise Exception('Message processor for "{}" not found'.format(path[0]))
        return operation(path[1:], get_params, post_params)

    @check_secret
    @execution_level('status')
    def process_status(self, path, get_params, post_params, server):
        """
        Returns client status (OS type or execution status) and login status
        :param path:
        :param get_params: optional parameter "detail" to show extended status
        :param post_params:
        :param server:
        :return: JSON object {"status": "status_code", "loggedin": boolean, ...}
        """
        st = {'linux': 'LNX', 'macos': 'OSX', 'windows': 'WIN'}
        try:
            # Standard status
            res = {'status': st[operations.os_type.lower()], 'loggedin': len(self.user) > 0}
            # Detailed status
            if get_params.get('detail', 'false') == 'true':
                res.update({'agent_version': VERSION, 'os_version': operations.os_version, 'sys_load': os.getloadavg()})
                if res['loggedin']:
                    res.update({'sessions': len(self.user), 'current_user': self.user[-1]})
        except KeyError:
            # Unknown operating system
            res = {'status': 'UNK'}
        return res

    @check_secret
    @execution_level('halt')
    def process_reboot(self, path, get_params, post_params, server):
        """
        Launches a system reboot operation
        :param path:
        :param get_params:
        :param post_params:
        :param server: authorization header
        :return: JSON object {"op": "launched"}
        """
        logger.debug('Received reboot operation')

        # Rebooting thread
        def rebt():
            operations.reboot()
        threading.Thread(target=rebt).start()
        return {'op': 'launched'}

    @check_secret
    @execution_level('halt')
    def process_poweroff(self, path, get_params, post_params, server):
        """
        Launches a system power off operation
        :param path:
        :param get_params:
        :param post_params:
        :param server: authorization header
        :return: JSON object {"op": "launched"}
        """
        logger.debug('Received poweroff operation')

        # Powering off thread
        def pwoff():
            time.sleep(2)
            operations.poweroff()
        threading.Thread(target=pwoff).start()
        return {'op': 'launched'}

    @check_secret
    @execution_level('full')
    def process_script(self, path, get_params, post_params, server):
        """
        Processes an script execution (script should be encoded in base64)
        :param path:
        :param get_params:
        :param post_params: JSON object {"script": "commands"}
        :param server: authorization header
        :return: JSON object {"op": "launched"}
        """
        logger.debug('Processing script request')
        # Decoding script (Windows scripts need a subprocess call per line)
        script = urllib.parse.unquote(post_params.get('script').decode('base64')).decode('utf8')
        if operations.os_type == 'Windows':
            script = 'import subprocess; {0}'.format(
                ';'.join(['subprocess.check_output({0},shell=True)'.format(repr(c)) for c in script.split('\n')]))
        else:
            script = 'import subprocess; subprocess.check_output("""{0}""",shell=True)'.format(script)
        # Executing script.
        if post_params.get('client', 'false') == 'false':
            thr = ScriptExecutorThread(script)
            thr.start()
        else:
            self.sendClientMessage('script', {'code': script})
        return {'op': 'launched'}

    @check_secret
    @execution_level('full')
    def process_logoff(self, path, get_params, post_params, server):
        """
        Closes user session
        """
        logger.debug('Received logoff operation')
        # Sending log off message to OGAgent client
        self.sendClientMessage('logoff', {})
        return {'op': 'sent to client'}

    @check_secret
    @execution_level('full')
    def process_popup(self, path, get_params, post_params, server):
        """
        Shows a message popup on the user's session
        """
        logger.debug('Received message operation')
        # Sending popup message to OGAgent client
        self.sendClientMessage('popup', post_params)
        return {'op': 'launched'}

    def process_client_popup(self, params):
        self.REST.sendMessage('popup_done', params)
