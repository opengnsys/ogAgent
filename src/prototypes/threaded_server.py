'''
Created on Jul 9, 2015

@author: dkmaster
'''


# Pydev can't parse "six.moves.xxxx" because it is loaded lazy
from six.moves.socketserver import ThreadingMixIn  # @UnresolvedImport
from six.moves.SimpleHTTPServer import SimpleHTTPRequestHandler  # @UnresolvedImport
from six.moves.BaseHTTPServer import HTTPServer  # @UnresolvedImport
from six.moves.urllib.parse import unquote  # @UnresolvedImport

import json
import threading
import ssl

import os.path
import tempfile

# For testing
# --------------------
CERTFILE = 'UDSActor.pem'


def createSelfSignedCert(force=False):

    certFile = os.path.join(tempfile.gettempdir(), CERTFILE)

    if os.path.exists(certFile) and not force:
        return certFile

    certData = '''-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCb50K3mIznNklz
yVAD7xSQOSJQ6+NPXj7U9/4zLZ+TvmbQ7RqUUsxbfxHbeRnoYTWV2nKk4+tHqmvz
ujLSS/loFhTSMqtrLn7rowSYJoQhKOUkAiQlWkqCfItWgL5pJopDpNHFul9Rn3ds
PMWQTiGeUNR4Y3RnBhr1Q1BsqAzf4m6zFUmgLPPmVLdF4uJ3Tuz8TSy2gWLs5aSr
5do4WamwUfYjRSVMJECmwjUM4rQ8SQgg0sHBeBuDUGNBvBQFac1G7qUcMReeu8Zr
DUtMsXma/l4rA8NB5CRmTrQbTBF4l+jb2BDFebDqDUK1Oqs9X35yOQfDOAFYHiix
PX0IsXOZAgMBAAECggEBAJi3000RrIUZUp6Ph0gzPMuCjDEEwWiQA7CPNX1gpb8O
dp0WhkDhUroWIaICYPSXtOwUTtVjRqivMoxPy1Thg3EIoGC/rdeSdlXRHMEGicwJ
yVyalFnatr5Xzg5wkxVh4XMd0zeDt7e3JD7s0QLo5lm1CEzd77qz6lhzFic5/1KX
bzdULtTlq60dazg2hEbcS4OmM1UMCtRVDAsOIUIZPL0M9j1C1d1iEdYnh2xshKeG
/GOfo95xsgdMlGjtv3hUT5ryKVoEsu+36rGb4VfhPfUvvoVbRx5QZpW+QvxaYh5E
Fi0JEROozFwG31Y++8El7J3yQko8cFBa1lYYUwwpNAECgYEAykT+GiM2YxJ4uVF1
OoKiE9BD53i0IG5j87lGPnWqzEwYBwnqjEKDTou+uzMGz3MDV56UEFNho7wUWh28
LpEkjJB9QgbsugjxIBr4JoL/rYk036e/6+U8I95lvYWrzb+rBMIkRDYI7kbQD/mQ
piYUpuCkTymNAu2RisK6bBzJslkCgYEAxVE23OQvkCeOV8hJNPZGpJ1mDS+TiOow
oOScMZmZpail181eYbAfMsCr7ri812lSj98NvA2GNVLpddil6LtS1cQ5p36lFBtV
xQUMZiFz4qVbEak+izL+vPaev/mXXsOcibAIQ+qI/0txFpNhJjpaaSy6vRCBYFmc
8pgSoBnBI0ECgYAUKCn2atnpp5aWSTLYgNosBU4vDA1PShD14dnJMaqyr0aZtPhF
v/8b3btFJoGgPMLxgWEZ+2U4ju6sSFhPf7FXvLJu2QfQRkHZRDbEh7t5DLpTK4Fp
va9vl6Ml7uM/HsGpOLuqfIQJUs87OFCc7iCSvMJDDU37I7ekT2GKkpfbCQKBgBrE
0NeY0WcSJrp7/oqD2sOcYurpCG/rrZs2SIZmGzUhMxaa0vIXzbO59dlWELB8pmnE
Tf20K//x9qA5OxDe0PcVPukdQlH+/1zSOYNliG44FqnHtyd1TJ/gKVtMBiAiE4uO
aSClod5Yosf4SJbCFd/s5Iyfv52NqsAyp1w3Aj/BAoGAVCnEiGUfyHlIR+UH4zZW
GXJMeqdZLfcEIszMxLePkml4gUQhoq9oIs/Kw+L1DDxUwzkXN4BNTlFbOSu9gzK1
dhuIUGfS6RPL88U+ivC3A0y2jT43oUMqe3hiRt360UQ1GXzp2dMnR9odSRB1wHoO
IOjEBZ8341/c9ZHc5PCGAG8=
-----END PRIVATE KEY-----
-----BEGIN CERTIFICATE-----
MIID7zCCAtegAwIBAgIJAIrEIthCfxUCMA0GCSqGSIb3DQEBCwUAMIGNMQswCQYD
VQQGEwJFUzEPMA0GA1UECAwGTWFkcmlkMREwDwYDVQQHDAhBbGNvcmNvbjEMMAoG
A1UECgwDVURTMQ4wDAYDVQQLDAVBY3RvcjESMBAGA1UEAwwJVURTIEFjdG9yMSgw
JgYJKoZIhvcNAQkBFhlzdXBwb3J0QHVkc2VudGVycHJpc2UuY29tMB4XDTE0MTAy
NjIzNDEyNFoXDTI0MTAyMzIzNDEyNFowgY0xCzAJBgNVBAYTAkVTMQ8wDQYDVQQI
DAZNYWRyaWQxETAPBgNVBAcMCEFsY29yY29uMQwwCgYDVQQKDANVRFMxDjAMBgNV
BAsMBUFjdG9yMRIwEAYDVQQDDAlVRFMgQWN0b3IxKDAmBgkqhkiG9w0BCQEWGXN1
cHBvcnRAdWRzZW50ZXJwcmlzZS5jb20wggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAw
ggEKAoIBAQCb50K3mIznNklzyVAD7xSQOSJQ6+NPXj7U9/4zLZ+TvmbQ7RqUUsxb
fxHbeRnoYTWV2nKk4+tHqmvzujLSS/loFhTSMqtrLn7rowSYJoQhKOUkAiQlWkqC
fItWgL5pJopDpNHFul9Rn3dsPMWQTiGeUNR4Y3RnBhr1Q1BsqAzf4m6zFUmgLPPm
VLdF4uJ3Tuz8TSy2gWLs5aSr5do4WamwUfYjRSVMJECmwjUM4rQ8SQgg0sHBeBuD
UGNBvBQFac1G7qUcMReeu8ZrDUtMsXma/l4rA8NB5CRmTrQbTBF4l+jb2BDFebDq
DUK1Oqs9X35yOQfDOAFYHiixPX0IsXOZAgMBAAGjUDBOMB0GA1UdDgQWBBRShS90
5lJTNvYPIEqP3GxWwG5iiDAfBgNVHSMEGDAWgBRShS905lJTNvYPIEqP3GxWwG5i
iDAMBgNVHRMEBTADAQH/MA0GCSqGSIb3DQEBCwUAA4IBAQAU0Sp4gXhQmRVzq+7+
vRFUkQuPj4Ga/d9r5Wrbg3hck3+5pwe9/7APoq0P/M0DBhQpiJKjrD6ydUevC+Y/
43ZOJPhMlNw0o6TdQxOkX6FDwQanLLs7sfvJvqtVzYn3nuRFKT3dvl7Zg44QMw2M
ay42q59fAcpB4LaDx/i7gOYSS5eca3lYW7j7YSr/+ozXK2KlgUkuCUHN95lOq+dF
trmV9mjzM4CNPZqKSE7kpHRywgrXGPCO000NvEGSYf82AtgRSFKiU8NWLQSEPdcB
k//2dsQZw2cRZ8DrC2B6Tb3M+3+CA6wVyqfqZh1SZva3LfGvq/C+u+ItguzPqNpI
xtvM
-----END CERTIFICATE-----'''
    with open(certFile, "wt") as f:
        f.write(certData)

    return certFile
# --------------


class HTTPServerHandler(SimpleHTTPRequestHandler):
    service = None
    protocol_version = 'HTTP/1.1'
    server_version = 'OpenGnsys Agent Server'
    sys_version = ''
    
    def sendJsonError(self, code, message):
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'error': message}))
        return

    def sendJsonResponse(self, data):
        self.send_response(200)
        data = json.dumps(data)
        self.send_header('Content-type', 'application/json')
        self.send_header('Content-Length', len(data))
        self.end_headers()
        # Send the html message
        self.wfile.write(data)
        
    
    # parseURL
    def parseUrl(self):
        # Very simple path & params splitter
        path = self.path.split('?')[0][1:].split('/')
        
        try:
            params = dict((v[0], unquote(v[1])) for v in (v.split('=') for v in self.path.split('?')[1].split('&')))
        except Exception:
            params = {}
        
        return (path, params)
    

    def do_GET(self):
        path, params = self.parseUrl()
        
        self.sendJsonResponse({'path': path, 'params': params})
        
    def do_POST(self):
        path, getParams = self.parseUrl()
        
        # Now post parameters, that are in JSON format
        
        
        
        

class HTTPThreadingServer(ThreadingMixIn, HTTPServer):
    pass

class HTTPServerThread(threading.Thread):
    def __init__(self, address, service):
        super(self.__class__, self).__init__()

        HTTPServerHandler.service = service

        self.certFile = createSelfSignedCert()
        self.server = HTTPThreadingServer(address, HTTPServerHandler)
        self.server.socket = ssl.wrap_socket(self.server.socket, certfile=self.certFile, server_side=True)

    def getServerUrl(self):
        return 'https://{}:{}/{}'.format(self.server.server_address[0], self.server.server_address[1], HTTPServerHandler.uuid)

    def stop(self):
        self.server.shutdown()

    def run(self):
        self.server.serve_forever()


if __name__ == '__main__':
    thr = HTTPServerThread(('0.0.0.0', 8000), None)
    print('Server started: {}'.format(thr))
    thr.start()

    