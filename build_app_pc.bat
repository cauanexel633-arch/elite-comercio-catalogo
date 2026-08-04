
@echo off
chcp 65001 >nul
echo ==========================================
echo  ELITE COMERCIO - APP PC DE VERDADE
echo  Com icone do selo anexado
echo  NAO abre navegador! Janela propria!
echo ==========================================
echo.
echo Verificando arquivos...
if not exist app.py (
    echo ERRO: app.py nao encontrado!
    pause
    exit /b
)
if not exist elite_icon.ico (
    echo ERRO: elite_icon.ico nao encontrado!
    echo Coloque o icone do selo na pasta!
    pause
    exit /b
)
if not exist elite_app.py (
    echo ERRO: elite_app.py nao encontrado!
    pause
    exit /b
)

echo [OK] app.py encontrado
echo [OK] elite_icon.ico encontrado (selo Elite)
echo [OK] elite_app.py encontrado

echo.
echo Instalando dependencias do APP NATIVO...
pip install pyinstaller flask python-dotenv google-genai pillow requests --upgrade --quiet

echo Instalando PyQt6 para janela nativa...
pip install PyQt6 PyQtWebEngine --quiet

echo Instalando pywebview (fallback)...
pip install pywebview --quiet

echo.
echo Limpando builds antigos...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q *.spec 2>nul

echo.
echo ==========================================
echo  Criando EXE APP NATIVO...
echo  Com icone do selo anexado
echo  Sem console, janela propria
echo ==========================================
echo.

pyinstaller --noconfirm --onefile --windowed --icon=elite_icon.ico --name="EliteComercio" --add-data="produtos;produtos" --add-data="site;site" --add-data="scripts;scripts" --add-data="logo.jpg;." --hidden-import=google.genai --hidden-import=google.genai.types --hidden-import=PIL --hidden-import=flask --hidden-import=dotenv --hidden-import=PyQt6 --hidden-import=PyQt6.QtWebEngineWidgets --hidden-import=webview elite_app.py

echo.
echo ==========================================
if exist dist\EliteComercio.exe (
    echo  ✅ APP NATIVO CRIADO COM SUCESSO!
    echo ==========================================
    echo.
    echo  Arquivo: dist\EliteComercio.exe
    echo  Tamanho:
    dir dist\EliteComercio.exe | find "EliteComercio"
    echo.
    echo  Tipo: Aplicativo para PC de verdade!
    echo  Janela: Propria, NAO abre Chrome/navegador
    echo  Icone: Selo Elite Comércio anexado!
    echo  Barra tarefas: Icone do selo
    echo  Console: NAO aparece (windowed)
    echo  Auto Sync: SIM
    echo  Liquid: SIM azul e amarelo com bolhas
    echo.
    echo  COMO USAR:
    echo  1. Va em dist\
    echo  2. Copie EliteComercio.exe para Desktop
    echo  3. Duplo clique
    echo  4. Abre JANELA DO APP, nao navegador!
    echo  5. Pode fixar na barra de tarefas
    echo.
) else (
    echo  ❌ ERRO ao criar EXE
    echo  Verifique os logs acima
    echo.
)

echo ==========================================
pause
