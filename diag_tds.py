# diag_tds.py — Inspeciona TODAS as tds da primeira linha do grid
# para identificar qual coluna contem o icone Doc.
# Execucao: python diag_tds.py

import sys, time, logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from scraper import QCertificaScraper, create_driver, _aguardar_carregamento

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("diag_tds.log", encoding="utf-8", mode="w"),
    ],
)
log = logging.getLogger("diag")

def main():
    driver = create_driver()
    scraper = QCertificaScraper(driver)
    try:
        scraper.login()
        scraper.navegar_fas903()
        scraper.aplicar_filtros()
        time.sleep(5)
        _aguardar_carregamento(driver)

        # Pega a primeira linha do grid
        rows = driver.find_elements(By.CSS_SELECTOR, "tr[id*='grdRemittance_ctl00__']")
        if not rows:
            log.info("ERRO: nenhuma linha encontrada no grid!")
            return

        log.info(f"Grid: {len(rows)} linhas. Inspecionando linha 0...")
        row = rows[0]
        row_id = row.get_attribute("id")
        log.info(f"Row id: {row_id}")

        # Dump de todas as tds via JS
        info = driver.execute_script("""
            var row = arguments[0];
            var tds = row.querySelectorAll('td');
            var result = [];
            for (var i = 0; i < tds.length; i++) {
                var td = tds[i];
                var children = [];
                td.querySelectorAll('*').forEach(function(el) {
                    children.push({
                        tag:     el.tagName,
                        id:      el.id || '',
                        cls:     (el.className || '').substring(0, 60),
                        onclick: (el.getAttribute('onclick') || '').substring(0, 80),
                        href:    (el.getAttribute('href') || '').substring(0, 80),
                        src:     (el.getAttribute('src') || '').substring(0, 80),
                        title:   (el.getAttribute('title') || '').substring(0, 40),
                        text:    (el.textContent || '').trim().substring(0, 30)
                    });
                });
                result.push({
                    idx:      i,
                    xpath_n:  i + 1,
                    html:     td.innerHTML.substring(0, 200),
                    text:     (td.textContent || '').trim().substring(0, 40),
                    onclick:  (td.getAttribute('onclick') || '').substring(0, 80),
                    children: children
                });
            }
            return result;
        """, row)

        log.info(f"Total de tds: {len(info)}")
        log.info("=" * 70)
        for td in info:
            has_link = any(
                c['tag'] in ('A', 'INPUT', 'BUTTON', 'IMG')
                or c['onclick']
                or c['href']
                or c['src']
                for c in td['children']
            )
            marker = " <-- CLICAVEL" if (has_link or td['onclick']) else ""
            log.info(
                f"td[{td['xpath_n']}] (idx={td['idx']}){marker}"
                f" | text='{td['text'][:30]}'"
                f" | onclick='{td['onclick'][:50]}'"
                f" | html='{td['html'][:100]}'"
            )
            for c in td['children']:
                if c['tag'] in ('A','INPUT','BUTTON','IMG') or c['onclick'] or c['href'] or c['src']:
                    log.info(
                        f"        {c['tag']} cls='{c['cls'][:40]}'"
                        f" onclick='{c['onclick'][:60]}'"
                        f" href='{c['href'][:60]}'"
                        f" src='{c['src'][:60]}'"
                        f" title='{c['title']}'"
                        f" text='{c['text'][:20]}'"
                    )
        log.info("=" * 70)

    except Exception as e:
        log.exception(f"Erro: {e}")
    finally:
        input("Pressione ENTER para fechar o browser...")
        driver.quit()

if __name__ == "__main__":
    main()
