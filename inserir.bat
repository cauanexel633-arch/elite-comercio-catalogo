@echo off
chcp 65001 >nul
title ELITE COMERCIO - Catalogo IA
echo ==========================================
echo  ELITE COMERCIO - APP LOCAL COM IA
echo ==========================================
cd /d %~dp0
if not exist venv (
  echo Criando ambiente virtual...
  python -m venv venv
)
call venv\Scripts\activate.bat
echo Instalando dependencias...
pip install -r requirements.txt --quiet
echo.
echo Abrindo app local...
python app.py
pause
