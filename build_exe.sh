#!/usr/bin/env bash
set -u
cd "D:/WB/2026-08-16-02-02-20/markitdown-gui" || exit 1
PYI="D:/WB/markitdown_packaging_venv/Scripts/pyinstaller.exe"
PIP="D:/WB/markitdown_packaging_venv/Scripts/python.exe -m pip"

# Reproducible build baseline (Stage 0/1B): ensure the declared build
# dependencies are present in the packaging venv before freezing. This pulls
# in `olefile` via `markitdown[outlook]` and pins markitdown/PySide6/PyInstaller.
"$PIP" install -r requirements.txt || {
  echo "WARN: pip install -r requirements.txt failed; continuing with current venv state" >&2
}
"$PYI" \
  --name md-desk \
  --onedir --windowed --noconfirm \
  --distpath dist --workpath build \
  --collect-submodules markitdown \
  --collect-data magika --collect-data pdfminer \
  --hidden-import pdfminer --hidden-import pdfminer.high_level --hidden-import pdfplumber --hidden-import pypdfium2 \
  --hidden-import mammoth --hidden-import pptx --hidden-import openpyxl --hidden-import pandas --hidden-import xlrd \
  --hidden-import bs4 --hidden-import markdownify --hidden-import defusedxml --hidden-import magika \
  --hidden-import charset_normalizer --hidden-import lxml --hidden-import requests --hidden-import PIL \
  --hidden-import cryptography --hidden-import cffi --hidden-import numpy \
  --hidden-import pydub --hidden-import speech_recognition \
  --exclude-module PySide6.QtNetwork --exclude-module PySide6.QtPdf --exclude-module PySide6.QtPdfWidgets \
  --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQuickWidgets --exclude-module PySide6.QtQuick3D \
  --exclude-module PySide6.Qt3DAnimation --exclude-module PySide6.Qt3DCore --exclude-module PySide6.Qt3DExtras --exclude-module PySide6.Qt3DInput --exclude-module PySide6.Qt3DLogic --exclude-module PySide6.Qt3DRender \
  --exclude-module PySide6.QtCharts --exclude-module PySide6.QtDataVisualization --exclude-module PySide6.QtBluetooth --exclude-module PySide6.QtLocation --exclude-module PySide6.QtPositioning --exclude-module PySide6.QtSerialPort \
  --exclude-module PySide6.QtSql --exclude-module PySide6.QtTest --exclude-module PySide6.QtDesigner --exclude-module PySide6.QtUiTools --exclude-module PySide6.QtHelp --exclude-module PySide6.QtNfc --exclude-module PySide6.QtScxml --exclude-module PySide6.QtSensors --exclude-module PySide6.QtGamepad --exclude-module PySide6.QtVirtualKeyboard --exclude-module PySide6.QtRemoteObjects --exclude-module PySide6.QtWebView \
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.QtWebEngineQuick \
  --exclude-module PySide6.QtMultimedia --exclude-module PySide6.QtMultimediaWidgets --exclude-module PySide6.QtXmlPatterns --exclude-module PySide6.QtXml --exclude-module PySide6.QtPrintSupport \
  main.py
echo "PYINSTALLER_EXIT=$?"
