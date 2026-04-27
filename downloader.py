# =============================================================================
# downloader.py — Download dos PDFs via modal "Documentos da remessa"
# =============================================================================
# Fluxo confirmado por inspecao DOM (test_popups v5):
#
#  Tabela principal -> cada linha tem:
#    td[3] (idx=2): input.btnGrid.btnDetails title="Visualizar Documentos"
#       -> clicando abre div.modalWindow id="...mdlDocuments_pnMain"
#
#  Dentro do modal:
#    A.btnGrid.btnPdf title="Clique para fazer o download do arquivo PDF"
#       -> javascript:__doPostBack(...) -> Chrome baixa o PDF
#    INPUT.modalCloseButton title="Fechar" -> fecha o modal
# =============================================================================

import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By

from config import DOWNLOAD_DIR, DOWNLOAD_WAIT, PAGE_LOAD_TIMEOUT
from utils import build_filename, load_checkpoint, log_download, logger, retry, save_checkpoint


# ---------------------------------------------------------------------------
# Aguardar download do PDF
# ---------------------------------------------------------------------------

def _aguardar_download_pdf(timeout=DOWNLOAD_WAIT, existentes=None):
    """
    Monitora DOWNLOAD_DIR e retorna Path do novo PDF quando concluir.
    existentes: snapshot dos PDFs ja presentes ANTES de clicar no botao.
                Se None, captura o snapshot agora (pode perder downloads rapidos).
    """
    prazo = time.time() + timeout
    if existentes is None:
        existentes = set(DOWNLOAD_DIR.glob("*.pdf"))

    while time.time() < prazo:
        em_progresso = (
            list(DOWNLOAD_DIR.glob("*.crdownload"))
            + list(DOWNLOAD_DIR.glob("*.part"))
        )
        if em_progresso:
            time.sleep(0.5)
            continue
        novos = [
            p for p in DOWNLOAD_DIR.glob("*.pdf")
            if p not in existentes and p.stat().st_size > 0
        ]
        if novos:
            return max(novos, key=lambda p: p.stat().st_mtime)
        time.sleep(0.5)

    return None


# ---------------------------------------------------------------------------
# Aguardar DOM estavel apos postbacks
# ---------------------------------------------------------------------------

def _aguardar_dom_estavel(driver, timeout: int = 10) -> None:
    """
    Aguarda document.readyState == 'complete' e ausencia de .crdownload.
    Usado apos fechar modal (postback AJAX pode re-renderizar o grid).
    """
    prazo = time.time() + timeout
    while time.time() < prazo:
        try:
            estado = driver.execute_script("return document.readyState")
            if estado == "complete":
                # Verifica se ha downloads em progresso
                if not list(DOWNLOAD_DIR.glob("*.crdownload")):
                    break
        except Exception:
            pass
        time.sleep(0.4)
    time.sleep(0.3)  # margem extra para AJAX Telerik


# ---------------------------------------------------------------------------
# Abrir modal clicando no btnDetails
# ---------------------------------------------------------------------------

def _abrir_modal(driver, elemento_doc):
    """
    Clica no input.btnGrid.btnDetails e aguarda o div.modalWindow aparecer.
    Retorna o ID do modal, ou None se nao detectado.
    """
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center',inline:'center'});",
            elemento_doc,
        )
        time.sleep(0.3)
        try:
            elemento_doc.click()
        except Exception:
            driver.execute_script("arguments[0].click();", elemento_doc)
        logger.debug("btnDetails clicado. Aguardando modal...")
    except Exception as exc:
        logger.warning("Nao foi possivel clicar no btnDetails: {}".format(exc))
        return None

    # Polling ate 8s pelo modal
    prazo = time.time() + 8
    while time.time() < prazo:
        modal_id = driver.execute_script("""
            var sels = ['.modalWindow','[id*="mdlDocuments"]','[class*="modalWindow"]'];
            for (var i = 0; i < sels.length; i++) {
                var els = document.querySelectorAll(sels[i]);
                for (var j = 0; j < els.length; j++) {
                    var s = window.getComputedStyle(els[j]);
                    if (s.display !== 'none' && s.visibility !== 'hidden'
                            && els[j].offsetHeight > 0) {
                        return els[j].id || '__modalWindow__';
                    }
                }
            }
            return null;
        """)
        if modal_id:
            logger.debug("Modal detectado: id='{}'".format(modal_id))
            return modal_id
        time.sleep(0.5)

    logger.warning("Modal nao apareceu em 8s.")
    return None


# ---------------------------------------------------------------------------
# Clicar no botao de download PDF dentro do modal
# ---------------------------------------------------------------------------

def _clicar_download_no_modal(driver, modal_id):
    """
    Dentro do modal, localiza o A.btnGrid.btnPdf e clica.
    Retorna True se clicou.
    """
    clicou = driver.execute_script("""
        var modal_id = arguments[0];

        // Localiza o modal
        var modal = document.getElementById(modal_id);
        if (!modal && modal_id === '__modalWindow__') {
            var els = document.querySelectorAll('.modalWindow,[id*="mdlDocuments"]');
            if (els.length > 0) modal = els[0];
        }
        if (!modal) return {ok: false, msg: 'modal nao encontrado'};

        // Estrategia 1: A.btnPdf (o correto)
        var pdf_btn = modal.querySelector('a.btnPdf, a[class*="btnPdf"]');
        if (pdf_btn) {
            pdf_btn.click();
            return {ok: true, metodo: 'a.btnPdf',
                    title: pdf_btn.getAttribute('title') || ''};
        }

        // Estrategia 2: por titulo exato
        var todos = modal.querySelectorAll('a,input[type="submit"],button');
        for (var i = 0; i < todos.length; i++) {
            var t = (todos[i].getAttribute('title') || '').toLowerCase();
            if (t.indexOf('pdf') !== -1 && t.indexOf('download') !== -1) {
                todos[i].click();
                return {ok: true, metodo: 'titulo:pdf+download',
                        title: todos[i].getAttribute('title') || ''};
            }
        }

        // Estrategia 3: por titulo parcial pdf
        for (var i = 0; i < todos.length; i++) {
            var t = (todos[i].getAttribute('title') || '').toLowerCase();
            var c = (todos[i].getAttribute('class') || '').toLowerCase();
            if (t.indexOf('pdf') !== -1 || c.indexOf('pdf') !== -1) {
                todos[i].click();
                return {ok: true, metodo: 'parcial:pdf',
                        title: todos[i].getAttribute('title') || ''};
            }
        }

        return {ok: false, msg: 'nenhum botao PDF encontrado no modal'};
    """, modal_id)

    if isinstance(clicou, dict) and clicou.get('ok'):
        logger.info("Download PDF clicado — metodo={} title='{}'".format(
            clicou.get('metodo'), clicou.get('title')))
        return True
    else:
        msg = clicou.get('msg') if isinstance(clicou, dict) else str(clicou)
        logger.error("Falha ao clicar no download PDF: {}".format(msg))
        return False


# ---------------------------------------------------------------------------
# Fechar modal
# ---------------------------------------------------------------------------

def _fechar_modal(driver, modal_id):
    """Fecha o modal clicando no INPUT.modalCloseButton (title='Fechar')."""
    try:
        driver.execute_script("""
            var modal_id = arguments[0];
            var modal = document.getElementById(modal_id);
            if (!modal && modal_id === '__modalWindow__') {
                var els = document.querySelectorAll('.modalWindow,[id*="mdlDocuments"]');
                if (els.length > 0) modal = els[0];
            }
            if (!modal) return;
            // Tenta botao fechar por classe ou titulo
            var fechar = modal.querySelector(
                'input.modalCloseButton, [title="Fechar"], [title="fechar"], [title="Close"]'
            );
            if (fechar) { fechar.click(); return; }
            // Fallback: background
            var bg = document.querySelector('.modalWindowBackground,[class*="modalBackground"]');
            if (bg) bg.click();
        """, modal_id)
        time.sleep(0.5)
        logger.debug("Modal fechado.")
    except Exception as exc:
        logger.debug("Aviso ao fechar modal: {}".format(exc))


# ---------------------------------------------------------------------------
# Download completo de um documento
# ---------------------------------------------------------------------------

@retry()
def baixar_documento_via_popup(driver, row_data):
    """
    Fluxo completo:
      1. Clica no btnDetails (abre modal)
      2. Dentro do modal, clica no A.btnPdf
      3. Aguarda PDF aparecer na pasta
      4. Renomeia e salva checkpoint
      5. Fecha modal
    """
    filename = build_filename(row_data)
    destino = DOWNLOAD_DIR / filename

    if destino.exists() and destino.stat().st_size > 0:
        logger.info("  Ja existe: {}".format(filename))
        log_download(row_data, "JA_EXISTE")
        return True

    elemento_doc = row_data.get("elemento_download")
    if not elemento_doc:
        logger.warning("  Sem elemento btnDetails para: {}".format(filename))
        log_download(row_data, "SEM_LINK")
        return False

    # Re-localiza o btnDetails pelo row_id para evitar StaleElementReferenceException
    # (o postback do download anterior pode ter atualizado o DOM)
    row_id = row_data.get("row_id", "")
    if row_id:
        try:
            from selenium.webdriver.common.by import By
            row_el = driver.find_element(By.ID, row_id)
            tds = row_el.find_elements(By.TAG_NAME, "td")
            if len(tds) > 2:
                btn = None
                try:
                    btn = tds[2].find_element(By.CSS_SELECTOR, "input.btnDetails")
                except Exception:
                    pass
                if btn is None:
                    for tag in ("input", "a", "button"):
                        c = tds[2].find_elements(By.TAG_NAME, tag)
                        if c:
                            btn = c[0]
                            break
                if btn:
                    elemento_doc = btn
                    logger.debug("  btnDetails re-localizado via row_id='{}'".format(row_id))
        except Exception as exc:
            logger.debug("  Re-localizacao falhou ({}), usando elemento original.".format(exc))

    logger.info("  Abrindo modal — remessa={} | {}".format(
        row_data.get("remessa"), filename))

    modal_id = _abrir_modal(driver, elemento_doc)

    if not modal_id:
        logger.error("  Modal nao abriu para remessa {}.".format(
            row_data.get("remessa")))
        log_download(row_data, "MODAL_NAO_ABRIU")
        return False

    # Snapshot dos PDFs existentes ANTES do clique — evita perder downloads rapidos
    existentes_antes = set(DOWNLOAD_DIR.glob("*.pdf"))

    clicou = _clicar_download_no_modal(driver, modal_id)

    pdf_baixado = (
        _aguardar_download_pdf(timeout=DOWNLOAD_WAIT, existentes=existentes_antes)
        if clicou else None
    )

    _fechar_modal(driver, modal_id)

    # Aguarda o DOM estabilizar apos fechar o modal (postback AJAX)
    _aguardar_dom_estavel(driver)

    if not clicou:
        logger.error("  Botao PDF nao encontrado no modal.")
        log_download(row_data, "BTN_PDF_NAO_ENCONTRADO")
        return False

    if pdf_baixado is None:
        logger.error("  Timeout aguardando PDF — remessa {}.".format(
            row_data.get("remessa")))
        log_download(row_data, "ERRO_TIMEOUT")
        return False

    if pdf_baixado != destino:
        try:
            pdf_baixado.rename(destino)
            logger.info("  Renomeado: {} -> {}".format(pdf_baixado.name, filename))
        except Exception as exc:
            logger.warning("  Nao renomeou {}: {}".format(pdf_baixado.name, exc))
            destino = pdf_baixado

    logger.info("  OK: {}".format(destino.name))
    save_checkpoint(filename)
    log_download(row_data, "OK")
    return True


# ---------------------------------------------------------------------------
# Orquestrador principal
# ---------------------------------------------------------------------------

def processar_downloads(driver, documentos: list) -> dict:
    """
    Processa a lista de documentos (linhas do grid) de uma pagina:
    baixa os PDFs via modal e registra resultados.
    Retorna resumo: {ok, pulados, erros, total}.
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint = load_checkpoint()

    ok = pulados = erros = 0
    total = len(documentos)

    for i, doc in enumerate(documentos, start=1):
        filename = build_filename(doc)
        logger.info("  [{}/{}] remessa={} | {}".format(
            i, total, doc.get("remessa"), filename))

        if filename in checkpoint:
            logger.info("  Pulado (checkpoint): {}".format(filename))
            pulados += 1
            continue

        sucesso = baixar_documento_via_popup(driver, doc)
        if sucesso:
            ok += 1
        else:
            erros += 1

        time.sleep(0.5)

    return {"ok": ok, "pulados": pulados, "erros": erros, "total": total}
