# =============================================================================
# utils.py — Helpers: logging, checkpoint, nomeação de arquivos, retry
# =============================================================================

import csv
import logging
import re
import time
from datetime import datetime
from functools import wraps
from pathlib import Path

from config import CHECKPOINT_FILE, LOG_FILE, MAX_RETRIES, RETRY_DELAY


# ── Logger ────────────────────────────────────────────────────────────────────

def setup_logger(name: str = "qcertifica") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # evita duplicar handlers

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Arquivo
    fh = logging.FileHandler("scraper.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


logger = setup_logger()


# ── Nomeação de arquivos ──────────────────────────────────────────────────────

def sanitize(text: str) -> str:
    """Remove caracteres inválidos para nome de arquivo."""
    return re.sub(r'[\\/:*?"<>|]', "_", text).strip()


def build_filename(row_data: dict) -> str:
    """
    Gera nome de arquivo padronizado a partir dos metadados da linha.
    Exemplo: Remessa_13101_Contrato_75295480.pdf
    """
    remessa = sanitize(row_data.get("remessa", "sem_remessa"))
    arquivo = sanitize(row_data.get("arquivo", "sem_arquivo"))
    # remove extensão duplicada se já vier no nome
    arquivo = re.sub(r"\.(xml|pdf)$", "", arquivo, flags=re.IGNORECASE)
    return f"Remessa_{remessa}_{arquivo}.pdf"


# ── Checkpoint (evitar re-download) ──────────────────────────────────────────

def load_checkpoint() -> set:
    """Retorna conjunto de nomes de arquivo já baixados."""
    if not CHECKPOINT_FILE.exists():
        return set()
    return set(CHECKPOINT_FILE.read_text(encoding="utf-8").splitlines())


def save_checkpoint(filename: str) -> None:
    """Registra um arquivo como baixado com sucesso."""
    with open(CHECKPOINT_FILE, "a", encoding="utf-8") as f:
        f.write(filename + "\n")


# ── Log CSV ───────────────────────────────────────────────────────────────────

def init_log() -> None:
    """Cria o cabeçalho do CSV de log se ainda não existir."""
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "timestamp", "remessa", "arquivo", "contratante",
                    "cedente", "recebimento", "fechamento", "status", "observacao"
                ],
            )
            writer.writeheader()


def log_download(row_data: dict, status: str, observacao: str = "") -> None:
    """Adiciona uma linha ao log CSV."""
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp", "remessa", "arquivo", "contratante",
                "cedente", "recebimento", "fechamento", "status", "observacao"
            ],
        )
        writer.writerow(
            {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "remessa": row_data.get("remessa", ""),
                "arquivo": row_data.get("arquivo", ""),
                "contratante": row_data.get("contratante", ""),
                "cedente": row_data.get("cedente", ""),
                "recebimento": row_data.get("recebimento", ""),
                "fechamento": row_data.get("fechamento", ""),
                "status": status,
                "observacao": observacao,
            }
        )


# ── Retry decorator ───────────────────────────────────────────────────────────

def retry(max_attempts: int = MAX_RETRIES, delay: float = RETRY_DELAY):
    """Decora uma função para tentar novamente em caso de exceção."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    if attempt == max_attempts:
                        logger.error(
                            f"{func.__name__} falhou após {max_attempts} tentativas: {exc}"
                        )
                        raise
                    logger.warning(
                        f"{func.__name__} — tentativa {attempt}/{max_attempts} falhou: {exc}. "
                        f"Aguardando {delay}s..."
                    )
                    time.sleep(delay)
        return wrapper
    return decorator
