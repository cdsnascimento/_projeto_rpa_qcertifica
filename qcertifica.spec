# qcertifica.spec — PyInstaller spec para Q-Certifica Downloader
# Gera um único executável Windows (.exe) sem console, com ícone personalizado.
# Execute via:  pyinstaller qcertifica.spec

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ---------------------------------------------------------------------------
# Hidden imports necessários para os pacotes usados
# ---------------------------------------------------------------------------

# Selenium carrega muitos submódulos dinamicamente — coleta todos de uma vez
selenium_imports = collect_submodules("selenium")

# webdriver_manager também usa importação dinâmica
wdm_imports = collect_submodules("webdriver_manager")

hidden_imports = (
    selenium_imports
    + wdm_imports
    + [
        # tkcalendar + babel
        "tkcalendar",
        "babel",
        "babel.numbers",
        "babel.dates",
        "babel.plural",
        # dotenv
        "dotenv",
        # pkg_resources / charset_normalizer
        "pkg_resources",
        "charset_normalizer",
        "charset_normalizer.md__mypyc",
        # módulos do projeto
        "scraper",
        "downloader",
        "config",
        "utils",
    ]
)

# Coleta arquivos de dados do babel (locale data — necessário para tkcalendar)
datas = collect_data_files("babel")

a = Analysis(
    ["app.py"],
    pathex=[str(Path(".").resolve())],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "IPython",
        "jupyter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="QCertifica",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # sem janela de console — app GUI
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="icon.ico",      # descomente e coloque o caminho do ícone se desejar
)
