
@echo off
echo ==========================================
echo  ELITE COMERCIO - APP NATIVO DE VERDADE
echo  Nao abre navegador! Janela propria!
echo ==========================================
echo.
echo Instalando dependencias app nativo...
pip install pywebview flask python-dotenv google-genai pillow requests --upgrade --quiet

echo Verificando PyQt6 (fallback)...
pip install PyQt6 PyQtWebEngine --quiet

echo.
echo Limpando...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q *.spec 2>nul

echo.
echo Criando EXE APP NATIVO com icone, sem console...
pyinstaller --noconfirm --onefile --windowed --icon=elite_icon.ico --name="EliteComercio" --add-data="produtos;produtos" --add-data="site;site" --add-data=".env;." --hidden-import=google.genai --hidden-import=google.genai.types --hidden-import=PIL --hidden-import=flask --hidden-import=dotenv --hidden-import=webview --hidden-import=PyQt6 --hidden-import=PyQt6.QtWebEngineWidgets elite_launcher_nativo.py

echo.
echo ==========================================
echo  ✅ APP NATIVO CRIADO!
echo ==========================================
echo  Arquivo: dist\EliteComercio.exe
echo  Tipo: Aplicativo de verdade!
echo  Janela: Propria, com icone, sem navegador
echo  Icone: elite_icon.ico na barra tarefas
echo  Console: NAO aparece
echo  Auto Sync: SIM
echo  Liquid: SIM azul/amarelo com bolhas
echo ==========================================
echo.
echo  Como usar:
echo  1. Duplo clique em EliteComercio.exe
echo  2. Abre janela do app (NAO abre Chrome)
echo  3. Parece programa instalado!
echo  4. Pode fixar na barra tarefas
echo.
pause
