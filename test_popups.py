# =============================================================================
# test_popups.py v5 — Detecta modalWindow, loga HTML e clica no download
# =============================================================================
import sys, time, logging
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from scraper import QCertificaScraper, create_driver, _aguardar_carregamento

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("test_popups.log", encoding="utf-8", mode="w"),
    ],
)
log = logging.getLogger("test_popups")

_ROW_CSS = "tr[id*='grdRemittance_ctl00__']"


# ---------------------------------------------------------------------------
# Verificar grid
# ---------------------------------------------------------------------------
def _verificar_grid(driver):
    info = driver.execute_script("""
        var rows = document.querySelectorAll("tr[id*='grdRemittance_ctl00__']");
        var ids = [];
        for (var i = 0; i < Math.min(rows.length, 3); i++) ids.push(rows[i].id);
        return {total: rows.length, ids: ids};
    """)
    log.info("Grid: {} linhas | ids={}".format(info.get('total', 0), info.get('ids')))
    return info.get('total', 0)


# ---------------------------------------------------------------------------
# Clicar no btnDetails (td[3], idx=2)
# ---------------------------------------------------------------------------
def _clicar_btn_details(driver, row_el, row_idx):
    tds = row_el.find_elements(By.TAG_NAME, "td")
    if len(tds) < 3:
        log.error("  Linha {}: apenas {} tds".format(row_idx, len(tds)))
        return False
    td = tds[2]
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", td)
    time.sleep(0.3)
    for tag in ("input", "a", "button"):
        try:
            el = td.find_element(By.TAG_NAME, tag)
            el.click()
            log.debug("  Linha {}: clicou <{}>".format(row_idx, tag))
            return True
        except Exception:
            continue
    try:
        ActionChains(driver).move_to_element(td).click().perform()
        log.debug("  Linha {}: ActionChains click".format(row_idx))
        return True
    except Exception as exc:
        log.error("  Linha {}: falha — {}".format(row_idx, exc))
        return False


# ---------------------------------------------------------------------------
# Aguardar e detectar o modalWindow
# ---------------------------------------------------------------------------
def _aguardar_modal(driver, row_idx, timeout=8):
    """
    Aguarda o div.modalWindow ficar visivel.
    Retorna o elemento do modal ou None.
    """
    prazo = time.time() + timeout
    while time.time() < prazo:
        modal = driver.execute_script("""
            var sels = [
                '.modalWindow',
                '[id*="mdlDocuments"]',
                '[class*="modalWindow"]',
                '[id*="pnMain"]'
            ];
            for (var i = 0; i < sels.length; i++) {
                var els = document.querySelectorAll(sels[i]);
                for (var j = 0; j < els.length; j++) {
                    var s = window.getComputedStyle(els[j]);
                    if (s.display !== 'none' && s.visibility !== 'hidden'
                            && els[j].offsetHeight > 0) {
                        return {
                            id:   els[j].id,
                            cls:  els[j].className,
                            html: els[j].innerHTML.substring(0, 2000)
                        };
                    }
                }
            }
            return null;
        """)
        if modal:
            log.info("  Linha {}: MODAL DETECTADO id='{}' cls='{}'".format(
                row_idx, modal['id'], modal['cls']))
            log.debug("  Modal HTML (2000 chars): {}".format(modal['html']))
            return modal
        time.sleep(0.5)
    log.warning("  Linha {}: modal nao apareceu em {}s".format(row_idx, timeout))
    return None


# ---------------------------------------------------------------------------
# Inspecionar botoes dentro do modal
# ---------------------------------------------------------------------------
def _inspecionar_modal(driver, modal_id):
    """Loga todos os elementos clicaveis dentro do modal."""
    info = driver.execute_script("""
        var modal = document.getElementById(arguments[0]);
        if (!modal) {
            var els = document.querySelectorAll('[class*="modalWindow"],[id*="mdlDocuments"]');
            if (els.length > 0) modal = els[0];
        }
        if (!modal) return {ok: false};
        var clicaveis = [];
        modal.querySelectorAll('a,input,button,img').forEach(function(e) {
            clicaveis.push({
                tag:    e.tagName,
                id:     e.id || '',
                cls:    (e.className || '').substring(0, 60),
                title:  e.getAttribute('title') || '',
                src:    (e.getAttribute('src') || '').substring(0, 80),
                href:   (e.getAttribute('href') || '').substring(0, 80),
                value:  e.getAttribute('value') || '',
                text:   (e.textContent || '').trim().substring(0, 40)
            });
        });
        var linhas = modal.querySelectorAll('tr');
        return {ok: true, clicaveis: clicaveis, linhas: linhas.length,
                html: modal.innerHTML.substring(0, 3000)};
    """, modal_id)
    if info.get('ok'):
        log.info("  Modal: {} linhas na tabela, {} elementos clicaveis".format(
            info.get('linhas', 0), len(info.get('clicaveis', []))))
        for c in info.get('clicaveis', []):
            log.info("    {} id='{}' cls='{}' title='{}' src='{}' href='{}' value='{}' text='{}'".format(
                c['tag'], c['id'], c['cls'], c['title'],
                c['src'][:50], c['href'][:50], c['value'], c['text']))
    return info


# ---------------------------------------------------------------------------
# Clicar no botao de download dentro do modal
# ---------------------------------------------------------------------------
def _clicar_download_modal(driver, modal_id, row_idx):
    """
    Dentro do modal, localiza o A.btnGrid.btnPdf e clica.
    Confirmado via inspecao DOM: cls='btnGrid btnPdf'
                                 title='Clique para fazer o download do arquivo PDF'
    """
    resultado = driver.execute_script("""
        var modal_id = arguments[0];
        var modal = document.getElementById(modal_id);
        if (!modal && modal_id === '__modalWindow__') {
            var els = document.querySelectorAll('.modalWindow,[id*="mdlDocuments"]');
            if (els.length > 0) modal = els[0];
        }
        if (!modal) return {ok: false, msg: 'modal nao encontrado'};

        // Estrategia 1: A.btnPdf (confirmado como o correto)
        var pdf_btn = modal.querySelector('a.btnPdf, a[class*="btnPdf"]');
        if (pdf_btn) {
            pdf_btn.click();
            return {ok: true, metodo: 'a.btnPdf',
                    tag: 'A', cls: pdf_btn.className,
                    title: pdf_btn.getAttribute('title') || ''};
        }

        // Estrategia 2: titulo contendo pdf + download
        var todos = modal.querySelectorAll('a,input[type="submit"],button');
        for (var i = 0; i < todos.length; i++) {
            var t = (todos[i].getAttribute('title') || '').toLowerCase();
            if (t.indexOf('pdf') !== -1 && t.indexOf('download') !== -1) {
                todos[i].click();
                return {ok: true, metodo: 'titulo:pdf+download',
                        tag: todos[i].tagName, cls: todos[i].className,
                        title: todos[i].getAttribute('title') || ''};
            }
        }

        // Estrategia 3: qualquer elemento com pdf na classe ou titulo
        for (var i = 0; i < todos.length; i++) {
            var t = (todos[i].getAttribute('title') || '').toLowerCase();
            var c = (todos[i].getAttribute('class') || '').toLowerCase();
            if (t.indexOf('pdf') !== -1 || c.indexOf('pdf') !== -1) {
                todos[i].click();
                return {ok: true, metodo: 'parcial:pdf',
                        tag: todos[i].tagName, cls: todos[i].className,
                        title: todos[i].getAttribute('title') || ''};
            }
        }

        return {ok: false, msg: 'nenhum botao PDF encontrado no modal'};
    """, modal_id)

    if resultado.get('ok'):
        log.info("  Linha {}: download clicado — metodo={} tag={} cls='{}' title='{}'".format(
            row_idx, resultado['metodo'], resultado['tag'],
            resultado['cls'], resultado['title']))
    else:
        log.warning("  Linha {}: {}".format(row_idx, resultado.get('msg')))
    return resultado.get('ok', False)


# ---------------------------------------------------------------------------
# Fechar modal
# ---------------------------------------------------------------------------
def _fechar_modal(driver, modal_id, row_idx):
    """Fecha o modal clicando no botao de fechar ou no background."""
    fechou = driver.execute_script("""
        // Tenta botao fechar por palavras-chave
        var modal = document.getElementById(arguments[0]);
        if (!modal) {
            var els = document.querySelectorAll('[class*="modalWindow"],[id*="mdlDocuments"]');
            if (els.length > 0) modal = els[0];
        }
        if (modal) {
            var btns = modal.querySelectorAll('a,input,button');
            var kws = ['fechar','close','cancel','cancelar','ok','x'];
            for (var i = 0; i < btns.length; i++) {
                var t = (btns[i].textContent || btns[i].value || btns[i].title || '').toLowerCase();
                for (var k = 0; k < kws.length; k++) {
                    if (t.indexOf(kws[k]) !== -1) {
                        btns[i].click();
                        return 'botao:' + t.trim().substring(0,20);
                    }
                }
            }
        }
        // Tenta clicar no background
        var bg = document.querySelector('.modalWindowBackground,[class*="modalBackground"]');
        if (bg) { bg.click(); return 'background'; }
        return null;
    """, modal_id)

    if fechou:
        log.debug("  Linha {}: modal fechado via '{}'".format(row_idx, fechou))
    else:
        log.warning("  Linha {}: nao conseguiu fechar modal".format(row_idx))
    time.sleep(0.5)


# ---------------------------------------------------------------------------
# Aguardar download de PDF
# ---------------------------------------------------------------------------
def _aguardar_pdf(download_dir, timeout=20):
    import os
    prazo = time.time() + timeout
    existentes = {f for f in os.listdir(download_dir) if f.endswith('.pdf')}
    while time.time() < prazo:
        em_andamento = [f for f in os.listdir(download_dir)
                        if f.endswith(('.crdownload', '.part'))]
        if em_andamento:
            time.sleep(1)
            continue
        novos = [f for f in os.listdir(download_dir)
                 if f.endswith('.pdf') and f not in existentes]
        if novos:
            return novos[0]
        time.sleep(1)
    return None


# ---------------------------------------------------------------------------
# Processar linha 0 da pagina 1 (modo diagnostico)
# ---------------------------------------------------------------------------
def _testar_linha(driver, pagina):
    from config import DOWNLOAD_DIR

    main_window = driver.current_window_handle
    total = _verificar_grid(driver)
    if total == 0:
        log.warning("Grid vazio.")
        return

    rows = driver.find_elements(By.CSS_SELECTOR, _ROW_CSS)
    log.info("Pagina {}: {} linhas. Testando APENAS a linha 0.".format(pagina, len(rows)))

    row_el  = rows[0]
    row_id  = row_el.get_attribute("id") or "row_0"
    log.info("Linha 0 | id='{}'".format(row_id))

    # Re-localiza para evitar StaleElement
    try:
        row_el = driver.find_element(By.ID, row_id)
    except Exception:
        pass

    # Clica no btnDetails
    clicou = _clicar_btn_details(driver, row_el, 0)
    if not clicou:
        log.error("Nao foi possivel clicar no btnDetails.")
        return

    # Aguarda o modal aparecer
    modal = _aguardar_modal(driver, 0, timeout=8)
    if not modal:
        log.error("Modal nao detectado.")
        return

    modal_id = modal['id']

    # Inspeciona elementos do modal
    _inspecionar_modal(driver, modal_id)

    # Tenta clicar no download
    baixou = _clicar_download_modal(driver, modal_id, 0)

    if baixou:
        log.info("Aguardando PDF em {}...".format(DOWNLOAD_DIR))
        pdf = _aguardar_pdf(str(DOWNLOAD_DIR), timeout=20)
        if pdf:
            log.info("PDF BAIXADO: {}".format(pdf))
        else:
            log.warning("Timeout aguardando PDF.")

    # Fecha o modal
    _fechar_modal(driver, modal_id, 0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    log.info("=" * 60)
    log.info("  test_popups v5 — iniciando")
    log.info("=" * 60)

    driver = create_driver()
    scraper = QCertificaScraper(driver)
    try:
        scraper.login()
        scraper.navegar_fas903()
        scraper.aplicar_filtros()
        log.info("Filtros aplicados. Aguardando grid...")
        time.sleep(4)
        _aguardar_carregamento(driver)
        _testar_linha(driver, 1)
    except KeyboardInterrupt:
        log.info("Interrompido.")
    except Exception as exc:
        log.exception("Erro: {}".format(exc))
    finally:
        log.info("=" * 60)
        log.info("  Concluido.")
        log.info("=" * 60)
        input("Pressione ENTER para fechar o browser...")
        driver.quit()


if __name__ == "__main__":
    main()
