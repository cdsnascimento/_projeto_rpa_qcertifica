@echo off
:: ============================================================
:: build.bat — Gera o executável QCertifica.exe
:: Execute este arquivo com duplo clique ou pelo terminal.
:: Requer Python 3.10+ instalado e no PATH.
:: ============================================================

echo.
echo  ============================================
echo   Q-Certifica — Build do Executavel
echo  ============================================
echo.

:: Verifica se Python está disponível
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH.
    echo Instale Python 3.10+ e adicione ao PATH.
    pause
    exit /b 1
)

:: Instala / atualiza dependências
echo [1/3] Instalando dependencias...
pip install --quiet --upgrade pyinstaller selenium webdriver-manager python-dotenv tkcalendar babel
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias.
    pause
    exit /b 1
)

:: Limpa build anterior (completo — sem cache do PyInstaller)
echo [2/3] Limpando build anterior...
if exist "dist\QCertifica.exe" del /f /q "dist\QCertifica.exe"
if exist "build"               rmdir /s /q "build"
if exist "dist"                rmdir /s /q "dist"
if exist "__pycache__"         rmdir /s /q "__pycache__"

:: Gera o executável
echo [3/3] Compilando o executavel (aguarde)...
python -m PyInstaller qcertifica.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERRO] A compilacao falhou. Veja as mensagens acima.
    pause
    exit /b 1
)

echo.
echo  ============================================
echo   Concluido! Executavel gerado em:
echo   dist\QCertifica.exe
echo  ============================================
echo.

:: Abre a pasta dist para facilitar o acesso
explorer dist

pause
