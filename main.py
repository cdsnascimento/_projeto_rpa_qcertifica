# =============================================================================
# main.py — Ponto de entrada do scraper Q-Certifica
# =============================================================================
# Uso:
#   1. Copie .env.example para .env e preencha suas credenciais.
#   2. Ajuste os filtros em config.py se necessário.
#   3. Execute:  python main.py

import sys

from downloader import processar_downloads
from scraper import (
    coletar_linhas_pagina,
    create_driver,
    ir_proxima_pagina,
    QCertificaScraper,
    tem_proxima_pagina,
)
from utils import init_log, logger


def main() -> None:
    logger.info("=" * 60)
    logger.info("  Q-Certifica Scraper — iniciando")
    logger.info("=" * 60)

    init_log()
    driver = create_driver()
    scraper = QCertificaScraper(driver)

    try:
        # 1. Login
        scraper.login()

        # 2. Navegar para FAS903
        scraper.navegar_fas903()

        # 3. Aplicar filtros (Aba Histórico já é selecionada dentro de aplicar_filtros)
        scraper.aplicar_filtros()

        # 4. Processar downloads (Paginado para evitar StaleElements)
        resumo = scraper.coletar_e_processar_downloads(processar_downloads)

        # 7. Relatório final
        logger.info("=" * 60)
        logger.info("  Concluído!")
        logger.info(f"  Total encontrado : {resumo['total']}")
        logger.info(f"  Baixados com êxito: {resumo['ok']}")
        logger.info(f"  Já existiam (pulados): {resumo['pulados']}")
        logger.info(f"  Erros           : {resumo['erros']}")
        logger.info("  Verifique downloads_log.csv para detalhes.")
        logger.info("=" * 60)

    except KeyboardInterrupt:
        logger.info("Interrompido pelo usuário.")
    except Exception as exc:
        logger.exception(f"Erro inesperado: {exc}")
        sys.exit(1)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
