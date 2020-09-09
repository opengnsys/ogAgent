#!/bin/bash
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


function process {
    pyuic5 about-dialog.ui -o about_dialog_ui.py -x
    pyuic5 message-dialog.ui -o message_dialog_ui.py -x
}

function process_qt4 {
    sed 's/OGAgent.qrc/OGAgent_qt4.qrc/' about-dialog.ui > about-dialog-qt4.ui
    pyuic4 about-dialog-qt4.ui -o about_dialog_qt4_ui.py -x
    pyuic4 message-dialog.ui -o message_dialog_qt4_ui.py -x
}    

cd $(dirname "$0")
[ -r VERSION ] && sed -i "s/Version [^<]*/Version $(cat VERSION)/" about-dialog.ui
pyrcc5 OGAgent.qrc -o OGAgent_rc.py
[ "$(command -v pyrcc4)" ] && pyrcc4 -py3 OGAgent.qrc -o OGAgent_qt4_rc.py


# process current directory ui's
process
[ "$(command -v pyuic4)" ] && process_qt4

