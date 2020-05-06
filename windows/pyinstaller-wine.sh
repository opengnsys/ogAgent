#!/bin/sh

# We need:
# * Wine (64 bit)
# * winetricks (in some distributions)

export WINEARCH=win64 WINEPREFIX=$PWD/wine WINEDEBUG=fixme-all
WINE=wine

# Get needed software
download() {
    mkdir -p downloads
    cd downloads
    wget -nd https://www.python.org/ftp/python/3.7.7/python-3.7.7-amd64.exe -O python3.msi
    wget -nd https://download.visualstudio.microsoft.com/download/pr/5e397ebe-38b2-4e18-a187-ac313d07332a/00945fbb0a29f63183b70370043e249218249f83dbc82cd3b46c5646503f9e27/vs_BuildTools.exe
    wget -nd https://prdownloads.sourceforge.net/nsis/nsis-3.05-setup.exe?download -O nsis-install.exe
    wget -nd http://nsis.sourceforge.net/mediawiki/images/d/d7/NSIS_Simple_Firewall_Plugin_1.20.zip
    cd ..
}

install_python() {
    cd downloads
    echo "Installing python"
    $WINE python3.msi /quiet TargetDir=C:\\Python37 PrependPath=1
    echo "Installing Build Tools for Visual Studio"
    $WINE vs_BuildTools.exe
    echo "Installing NSIS (needs X?)"
    $WINE nsis-install.exe /S
    cd ..
}

setup_pip() {
    echo "Setting up pip and setuptools"
    $WINE pip install --upgrade pip
    $WINE pip install --upgrade setuptools
}

install_packages() {
    echo "Installing PyQt5"
    $WINE pip install PyQt5
    echo "Installing required packages"
    $WINE pip install pycrypto requests six
    # Using easy_install instead of pip to install pycrypto
    $WINE pip install pycrypto
    echo "Installing PyInstaller"
    $WINE pip install PyInstaller
    echo "Copying simple firewall plugin for nsis installer"
    unzip -o downloads/NSIS_Simple_Firewall_Plugin_1.20.zip SimpleFC.dll -d $WINEPREFIX/drive_c/Program\ Files/NSIS/Plugins/x86-ansi/
    unzip -o downloads/NSIS_Simple_Firewall_Plugin_1.20.zip SimpleFC.dll -d $WINEPREFIX/drive_c/Program\ Files/NSIS/Plugins/x86-unicode/
}

download
install_python
setup_pip
install_packages

