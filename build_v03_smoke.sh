#!/usr/bin/env bash
set -u
cd "D:/WB/2026-08-16-02-02-20/markitdown-gui" || exit 1
PYI="D:/WB/markitdown_packaging_venv/Scripts/pyinstaller.exe"
PIP="D:/WB/markitdown_packaging_venv/Scripts/python.exe -m pip"

# Keep the build baseline in sync with the product EXE (same deps + flags),
# then build the hermetic v0.3 AI/OCR smoke as a CONSOLE executable so its
# PASS/FAIL output is visible (the product md-desk.exe is --windowed).
"$PIP" install -r requirements.txt || {
  echo "WARN: pip install -r requirements.txt failed; continuing with current venv state" >&2
}
"$PYI" \
  --name md-desk-v03-smoke \
  --onedir --console --noconfirm \
  --distpath dist --workpath build_v03_smoke \
  --collect-submodules markitdown \
  --collect-submodules markitdown_ocr \
  --collect-data magika --collect-data pdfminer \
  --hidden-import pdfminer --hidden-import pdfminer.high_level --hidden-import pdfplumber --hidden-import pypdfium2 \
  --hidden-import mammoth --hidden-import pptx --hidden-import openpyxl --hidden-import pandas --hidden-import xlrd \
  --hidden-import bs4 --hidden-import markdownify --hidden-import defusedxml --hidden-import magika \
  --hidden-import charset_normalizer --hidden-import lxml --hidden-import requests --hidden-import PIL \
  --hidden-import cryptography --hidden-import cffi --hidden-import numpy \
  --hidden-import openai --hidden-import pydub --hidden-import speech_recognition \
  --exclude-module PySide6.QtNetwork --exclude-module PySide6.QtPdf --exclude-module PySide6.QtPdfWidgets \
  --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQuickWidgets --exclude-module PySide6.QtQuick3D \
  --exclude-module PySide6.Qt3DAnimation --exclude-module PySide6.Qt3DCore --exclude-module PySide6.Qt3DExtras --exclude-module PySide6.Qt3DInput --exclude-module PySide6.Qt3DLogic --exclude-module PySide6.Qt3DRender \
  --exclude-module PySide6.QtCharts --exclude-module PySide6.QtDataVisualization --exclude-module PySide6.QtBluetooth --exclude-module PySide6.QtLocation --exclude-module PySide6.QtPositioning --exclude-module PySide6.QtSerialPort \
  --exclude-module PySide6.QtSql --exclude-module PySide6.QtTest --exclude-module PySide6.QtDesigner --exclude-module PySide6.QtUiTools --exclude-module PySide6.QtHelp --exclude-module PySide6.QtNfc --exclude-module PySide6.QtScxml --exclude-module PySide6.QtSensors --exclude-module PySide6.QtGamepad --exclude-module PySide6.QtVirtualKeyboard --exclude-module PySide6.QtRemoteObjects --exclude-module PySide6.QtWebView \
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.QtWebEngineQuick \
  --exclude-module PySide6.QtMultimedia --exclude-module PySide6.QtMultimediaWidgets --exclude-module PySide6.QtXmlPatterns --exclude-module PySide6.QtXml --exclude-module PySide6.QtPrintSupport \
  tests/exe_v03_smoke.py
echo "PYINSTALLER_EXIT=$?"
