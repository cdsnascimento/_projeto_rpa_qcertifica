# config.py - Configuracoes e filtros do scraper Q-Certifica (FAS903)
# Edite este arquivo para ajustar filtros e comportamento sem tocar na logica.

import sys
from pathlib import Path

# Quando empacotado com PyInstaller (--onefile ou --onedir), __file__ aponta para
# a pasta temporária de extração. Usamos sys.executable para gravar dados ao lado
# do .exe; em modo de desenvolvimento, usamos o diretório do próprio script.
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
LOG_FILE = BASE_DIR / "downloads_log.csv"
CHECKPOINT_FILE = BASE_DIR / "checkpoint.txt"

# URLs
BASE_URL = "https://portal.qcertifica.com.br"
LOGIN_URL = f"{BASE_URL}/"
FAS903_URL = f"{BASE_URL}/DigitalSignature/FAS903.aspx"

# Filtros da tela FAS903 -> aba Historico
# Campos de lookup: codigo dispara Tab -> plataforma preenche o nome automaticamente
# Deixe o valor como "" para nao preencher o campo.
FILTROS = {
    "contratante_codigo": "67632",
    "contratante_nome": "Red Fidc Multisetorial Lp",
    "usuario_codigo": "60895",
    "usuario_nome": "ALENCAR CESAR MARTINS ZAMBONI",
    "cedente": "",
    "remessa": "",
    "tipo_doc": "",           # texto visivel no dropdown; "" = todos
    "documento_de": "",       # formato DD/MM/AAAA
    "documento_ate": "",
    "fechamento_de": "01/01/2022",
    "fechamento_ate": "30/04/2022",
    "num_titulo": "",
    "arquivo": "",
}

# Selenium
HEADLESS = False          # True = sem abrir janela
PAGE_LOAD_TIMEOUT = 30    # segundos
IMPLICIT_WAIT = 2         # reduzido de 10 -> 2 para nao travar em seletores falhos
DOWNLOAD_WAIT = 15        # segundos aguardando download concluir

# Retry
MAX_RETRIES = 3
RETRY_DELAY = 5           # segundos entre tentativas

# Paginacao
ROWS_PER_PAGE = 50        # linhas por pagina (se o dropdown existir)
