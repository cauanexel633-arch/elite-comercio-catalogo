
@echo off
echo Testando APP NATIVO sem criar EXE...
echo.
echo Instalando pywebview e PyQt6...
pip install pywebview PyQt6 PyQtWebEngine flask python-dotenv google-genai --quiet
echo.
echo Iniciando APP NATIVO...
echo Nao vai abrir navegador, vai abrir janela propria!
python elite_app.py
pause
