@echo off
echo ==========================================
echo  ELITE COMERCIO - APP PC - FIX QT
echo  Corrigindo conflito PyQt5 vs PyQt6
echo ==========================================
echo.

echo Limpando PyQt5 para evitar conflito...
pip uninstall PyQt5 PyQt5-sip PyQt5-Qt5 -y 2>nul

echo.
echo Verificando arquivos...
if not exist app.py (
    echo ERRO: app.py nao encontrado
    pause
    exit /b
)
if not exist elite_icon.ico (
    echo ERRO: elite_icon.ico nao encontrado
    pause
    exit /b
)
if not exist elite_app.py (
    echo ERRO: elite_app.py nao encontrado
    pause
    exit /b
)

echo [OK] app.py
echo [OK] elite_icon.ico
echo [OK] elite_app.py
echo.

echo Instalando apenas PyQt6...
pip install PyQt6 PyQtWebEngine --quiet --upgrade

echo.
echo Limpando builds antigos...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q *.spec 2>nul
del /q EliteComercio.spec 2>nul

echo.
echo Criando EXE com fix para Qt...
echo Isso pode demorar 3-5 minutos...
echo.

REM Usa --exclude para remover PyQt5 que causa conflito
pyinstaller --noconfirm --onefile --windowed --icon=elite_icon.ico --name=EliteComercio --add-data=produtos;produtos --add-data=site;site --exclude-module PyQt5 --exclude-module PyQt5.QtCore --exclude-module PyQt5.QtGui --exclude-module PyQt5.QtWidgets --exclude-module PyQt5.sip --exclude-module PySide2 --exclude-module PySide6 --exclude-module PyQt5-Qt5 --hidden-import=google.genai --hidden-import=flask --hidden-import=PyQt6 --hidden-import=PyQt6.QtCore --hidden-import=PyQt6.QtGui --hidden-import=PyQt6.QtWidgets --hidden-import=PyQt6.QtWebEngineWidgets elite_app.py

echo.
echo ==========================================
if exist dist\EliteComercio.exe (
    echo  EXE CRIADO COM SUCESSO
    echo ==========================================
    echo.
    echo  Arquivo: dist\EliteComercio.exe
    dir dist\EliteComercio.exe
    echo.
    echo  Tipo: App PC com icone do selo
    echo  Janela: Propria
    echo.
    echo  COMO USAR:
    echo  1. Copie para Desktop
    echo  2. Duplo clique
    echo  3. Abre janela do app
    echo.
) else (
    echo  ERRO - Tentando metodo alternativo...
    echo.
    echo  Criando com pywebview apenas...
    pip uninstall PyQt6 PyQtWebEngine -y 2>nul
    pip install pywebview --quiet
    
    rmdir /s /q build 2>nul
    rmdir /s /q dist 2>nul
    del /q *.spec 2>nul
    
    pyinstaller --noconfirm --onefile --windowed --icon=elite_icon.ico --name=EliteComercio --add-data=produtos;produtos --add-data=site;site --exclude-module PyQt5 --exclude-module PyQt6 --hidden-import=google.genai --hidden-import=flask --hidden-import=webview elite_app.py
    
    if exist dist\EliteComercio.exe (
        echo EXE criado com pywebview!
    ) else (
        echo Falha nos dois metodos
    )
)
echo ==========================================
pause
