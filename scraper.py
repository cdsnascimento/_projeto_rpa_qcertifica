# scraper.py — Refatorado v4
#
# Mudancas desta versao:
#  - XPath com ID exato para todos os campos do painel PV1 (aba Historico)
#  - LOV: Selenium .click() REAL (nao JS) — Chrome reconhece como gesto do usuario
#  - Popup LOV: detecta nova janela OU RadWindow iframe (mesmo contexto)
#  - Tab fallback com send_keys real se popup nao abrir
#  - Verificacao pos-lookup: loga se campo description/name foi preenchido pelo servidor

import os
import time

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from config import (
    DOWNLOAD_DIR,
    FAS903_URL,
    FILTROS,
    HEADLESS,
    IMPLICIT_WAIT,
    LOGIN_URL,
    PAGE_LOAD_TIMEOUT,
    ROWS_PER_PAGE,
)
from utils import logger, retry

load_dotenv()

# --------------------------------------------------------------------------- #
# XPaths e IDs dos campos do formulario — painel PV1 (aba Historico)          #
# Confirmados via inspecao do DOM na sessao anterior                           #
# --------------------------------------------------------------------------- #

_PV1      = "ctl00_cphContext_tabManager_PV1_UC0_frvDocument"
_GRID_ID  = "ctl00_cphContext_tabManager_PV1_UC0_grdRemittance"

_XP = {
    # Contratante
    "company_code":  f'//*[@id="{_PV1}_txbCompanyCode"]',
    "company_desc":  f'//*[@id="{_PV1}_txbCompanyDescription"]',
    "company_lov":   f'//*[@id="btnLOV{_PV1}_lovCompany"]',

    # Usuario
    "user_code":     f'//*[@id="{_PV1}_txbUserCode"]',
    "user_name":     f'//*[@id="{_PV1}_txbUserName"]',
    "user_lov":      f'//*[@id="btnLOV{_PV1}_lovUser"]',

    # Datas de fechamento (RadDatePicker — campo visivel)
    "date_from":     f'//*[@id="{_PV1}_txbRemittanceDateFrom_dateInput"]',
    "date_to":       f'//*[@id="{_PV1}_txbRemittanceDateTo_dateInput"]',

    # IDs puros para ClientState (usados em document.getElementById)
    "date_from_input_id": f"{_PV1}_txbRemittanceDateFrom_dateInput",
    "date_to_input_id":   f"{_PV1}_txbRemittanceDateTo_dateInput",

    # Botao Buscar
    "btn_find":      f'//*[@id="{_PV1}_btnFind"]',
}


# XPath confirmado em inspecao DOM — botao "Proxima pagina" do pager
_XPATH_NEXT_PAGE = (
    '//*[@id="ctl00_cphContext_tabManager_PV1_UC0_grdRemittance_ctl00_Pager"]'
    '/tbody/tr/td/table/tbody/tr/td/div[3]/input[1]'
)

# --------------------------------------------------------------------------- #
# Driver                                                                       #
# --------------------------------------------------------------------------- #

def create_driver() -> webdriver.Chrome:
    """Cria e configura o Chrome WebDriver com preferencias de download de PDF."""
    prefs = {
        "download.default_directory": str(DOWNLOAD_DIR.resolve()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
    }
    options = Options()
    if HEADLESS:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_experimental_option("prefs", prefs)
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.implicitly_wait(IMPLICIT_WAIT)
    return driver


# --------------------------------------------------------------------------- #
# Utilitario de espera                                                         #
# --------------------------------------------------------------------------- #

def _aguardar_carregamento(driver: webdriver.Chrome, timeout: int = 15) -> None:
    """
    Aguarda document.readyState == 'complete' e ausencia de overlays Telerik.
    """
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except Exception:
        pass
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: not d.execute_script(
                """
                var els=document.querySelectorAll(
                    '.RadAjaxPanel,.raDiv,[class*="Loading"],[class*="loading"]');
                for(var i=0;i<els.length;i++){
                    var s=window.getComputedStyle(els[i]);
                    if(s.display!=='none'&&s.visibility!=='hidden'&&parseFloat(s.opacity)>0)
                        return true;
                }
                return false;
                """
            )
        )
    except Exception:
        pass
    time.sleep(0.5)


# --------------------------------------------------------------------------- #
# Classe principal                                                              #
# --------------------------------------------------------------------------- #

class QCertificaScraper:

    def __init__(self, driver: webdriver.Chrome):
        self.driver = driver
        self.wait = WebDriverWait(self.driver, PAGE_LOAD_TIMEOUT)

    # ---------------------------------------------------------------------- #
    # Helpers internos                                                        #
    # ---------------------------------------------------------------------- #

    def _tratar_popup_sessao_duplicada(self, timeout: float = 6.0) -> None:
        """
        Detecta e dispensa o popup 'usuário já logado em outro local'.
        O popup aparece esporadicamente após o submit do formulário de login.
        Estratégia: procura o botão 'Continuar' dentro de um timeout curto;
        se não aparecer, retorna silenciosamente sem lançar exceção.
        """
        import time as _time

        _XPATH_CONTINUAR = '//*[@id="ctl00_body_btnSimUsuarioLogado"]'

        deadline = _time.monotonic() + timeout
        while _time.monotonic() < deadline:
            btns = self.driver.find_elements(By.XPATH, _XPATH_CONTINUAR)
            if btns:
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", btns[0])
                    btns[0].click()
                    logger.info("Popup 'sessão duplicada' detectado — clicado em Continuar.")
                    _time.sleep(1.0)   # aguarda o portal processar o clique
                    return
                except Exception as e:
                    logger.debug("Popup 'sessão duplicada': erro ao clicar — %s", e)
            _time.sleep(0.4)

        # Nenhum popup encontrado — caminho normal, sem erro
        logger.debug("Popup 'sessão duplicada' não apareceu (normal).")

    # ---------------------------------------------------------------------- #
    # Login                                                                   #
    # ---------------------------------------------------------------------- #

    def login(self) -> None:
        """Realiza o login com CPF e senha."""
        username = os.getenv("QCERTIFICA_USER")
        password = os.getenv("QCERTIFICA_PASS")
        if not username or not password:
            raise ValueError("Credenciais nao encontradas no .env")

        logger.info(f"Acessando {LOGIN_URL}...")
        self.driver.get(LOGIN_URL)

        campo_usuario = self.wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "input[type='text']:not([readonly]):not([disabled])")
            )
        )
        campo_senha = self.driver.find_element(By.CSS_SELECTOR, "input[type='password']")

        self.driver.execute_script("arguments[0].value = '';", campo_usuario)
        campo_usuario.send_keys(username)
        self.driver.execute_script("arguments[0].value = '';", campo_senha)
        campo_senha.send_keys(password)
        campo_senha.send_keys(Keys.RETURN)

        # Trata popup "usuário já logado em outro local" — aparece esporadicamente
        self._tratar_popup_sessao_duplicada()

        self.wait.until(lambda d: "login" not in d.current_url.lower())
        logger.info("Login realizado com sucesso.")

    # ---------------------------------------------------------------------- #
    # Navegacao                                                               #
    # ---------------------------------------------------------------------- #

    def navegar_fas903(self) -> None:
        """Navega para a tela FAS903."""
        logger.info(f"Navegando para FAS903: {FAS903_URL}")
        self.driver.get(FAS903_URL)
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "form")))
        _aguardar_carregamento(self.driver)
        logger.info("Tela FAS903 carregada.")

    # ---------------------------------------------------------------------- #
    # Selecao de aba                                                          #
    # ---------------------------------------------------------------------- #

    def selecionar_aba_historico(self) -> None:
        """
        Seleciona a aba Historico via JS puro — 3 estrategias, sem StaleElement.
        """
        logger.info("Selecionando aba Historico...")
        resultado = self.driver.execute_script("""
            try {
                var ts=(window.$find)?$find('ctl00_cphContext_tabManager_tbsMain'):null;
                if(ts){
                    var tabs=ts.get_tabs();
                    for(var i=0;i<tabs.get_count();i++){
                        var tab=tabs.getTab(i);
                        var txt=(tab.get_text)?tab.get_text():'';
                        if(txt&&txt.indexOf('Hist')!==-1){tab.click();return 'api:'+i+':'+txt;}
                    }
                }
            }catch(e1){}
            try{
                var hid=document.getElementById('ctl00_cphContext_tabManager_hidSelectedTabValue');
                var btn=document.getElementById('ctl00_cphContext_tabManager_btnTabTrigger');
                if(hid&&btn){hid.value='1';btn.click();return 'trigger:ok';}
            }catch(e2){}
            try{
                var sels=['a.rtsLink','li.rtsLI > a','.RadTabStrip a'];
                for(var si=0;si<sels.length;si++){
                    var els=document.querySelectorAll(sels[si]);
                    for(var j=0;j<els.length;j++){
                        var t=(els[j].textContent||els[j].innerText||'').trim();
                        if(t.indexOf('Hist')!==-1){els[j].click();return 'dom:'+t;}
                    }
                }
            }catch(e3){}
            return null;
        """)
        if resultado:
            logger.info(f"Aba Historico acionada: {resultado}")
            time.sleep(3)
            _aguardar_carregamento(self.driver)
        else:
            logger.warning("Nao foi possivel acionar aba Historico.")

    # ---------------------------------------------------------------------- #
    # Lookup via LOV com XPath exato                                          #
    # ---------------------------------------------------------------------- #

    def _preencher_lookup_lov(
        self,
        xpath_codigo: str,
        xpath_desc: str,
        xpath_botao: str,
        codigo: str,
        label: str,
    ) -> bool:
        """
        Preenche campo de lookup usando XPath com ID exato:
          1. Digita o codigo no campo (send_keys real)
          2. Clica no botao LOV com Selenium .click() REAL
             (nao JS — Chrome so abre popup com clique genuino)
          3. Aguarda RadWindow iframe OU nova janela
          4. No popup: clica no primeiro resultado valido
          5. Verifica campo de descricao como confirmacao
          6. Fallback: Tab key se popup nao abrir
        """
        # 1. Preenche o campo de codigo
        try:
            campo = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, xpath_codigo))
            )
            self.driver.execute_script("arguments[0].value='';", campo)
            campo.send_keys(codigo)
            logger.debug(f"{label}: codigo '{codigo}' digitado.")
        except Exception as exc:
            logger.warning(f"{label}: campo de codigo nao encontrado — {exc}")
            return False

        # 2. Clica no botao LOV com click() REAL do Selenium
        main_window = self.driver.current_window_handle
        janelas_antes = set(self.driver.window_handles)

        try:
            btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, xpath_botao))
            )
            btn.click()
            logger.info(f"{label}: botao LOV clicado (Selenium real click).")
        except Exception as exc:
            logger.warning(f"{label}: botao LOV indisponivel ({exc}). Usando Tab key...")
            self._tab_fallback(xpath_codigo, xpath_desc, codigo, label)
            return True

        time.sleep(3)  # Aguarda popup abrir (RadWindow pode demorar)

        # 3. Detecta tipo de popup: nova janela vs RadWindow iframe
        novas_janelas = set(self.driver.window_handles) - janelas_antes
        popup_tipo = None

        if novas_janelas:
            popup_handle = novas_janelas.pop()
            self.driver.switch_to.window(popup_handle)
            popup_tipo = "janela"
            logger.info(f"{label}: popup abriu em nova janela do browser.")
        else:
            # Telerik RadWindow — iframe embutido na mesma pagina
            # Loga todos os iframes presentes para debug
            iframes_info = self.driver.execute_script("""
                var ifs=document.querySelectorAll('iframe');
                var r=[];
                for(var i=0;i<ifs.length;i++){
                    r.push({id:ifs[i].id,src:ifs[i].src,
                             cls:ifs[i].className,
                             parent:(ifs[i].parentElement?ifs[i].parentElement.className:'')});
                }
                return r;
            """)
            logger.debug(f"{label}: iframes na pagina = {iframes_info}")

            seletores_iframe = (
                ".RadWindow iframe",
                "[class*='RadWindow'] iframe",
                "[id*='RadWindowWrapper'] iframe",
                "[id*='dlgLOV'] iframe",
                "iframe[src*='LOV']",
                "iframe[src*='lov']",
                "iframe[src*='FAS']",
                "iframe[src*='Lookup']",
                "iframe[src*='lookup']",
                "iframe",  # fallback: qualquer iframe novo
            )
            for sel in seletores_iframe:
                try:
                    iframe = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                    )
                    self.driver.switch_to.frame(iframe)
                    popup_tipo = "iframe"
                    logger.info(f"{label}: RadWindow iframe detectado ({sel}).")
                    break
                except Exception:
                    continue

        if popup_tipo is None:
            logger.warning(f"{label}: popup nao detectado. Usando Tab key...")
            self._tab_fallback(xpath_codigo, xpath_desc, codigo, label)
            return True

        # 4. Dentro do popup: clica no primeiro resultado valido
        try:
            _aguardar_carregamento(self.driver)
            time.sleep(1.5)

            clicou = self.driver.execute_script("""
                var els=document.querySelectorAll('a,input[type="button"],input[type="submit"]');
                for(var i=0;i<els.length;i++){
                    var t=(els[i].textContent||els[i].value||'').trim().toLowerCase();
                    if(t&&t.indexOf('selec')!==-1){els[i].click();return 'selecionar:'+t;}
                }
                var rows=document.querySelectorAll('table tr');
                for(var r=1;r<rows.length;r++){
                    var link=rows[r].querySelector('td a,td input[type="button"]');
                    if(link){
                        var t2=(link.textContent||link.value||'').trim();
                        if(t2){link.click();return 'row:'+t2;}
                    }
                }
                var tda=document.querySelectorAll('td a');
                if(tda.length>0){tda[0].click();return 'td_a:'+tda[0].textContent.trim();}
                return null;
            """)
            if clicou:
                logger.info(f"{label}: item selecionado no popup — {clicou}")
            else:
                logger.warning(f"{label}: nenhum item clicavel encontrado no popup.")
        except Exception as exc:
            logger.warning(f"{label}: erro ao interagir no popup — {exc}")

        # 5. Volta ao contexto principal
        if popup_tipo == "janela":
            try:
                WebDriverWait(self.driver, 8).until(
                    lambda d: len(d.window_handles) == len(janelas_antes)
                )
            except Exception:
                try:
                    self.driver.close()
                except Exception:
                    pass
            self.driver.switch_to.window(main_window)
        else:
            self.driver.switch_to.default_content()

        _aguardar_carregamento(self.driver)

        # 6. Verifica confirmacao: campo descricao preenchido?
        try:
            desc_el = self.driver.find_element(By.XPATH, xpath_desc)
            desc_valor = (desc_el.get_attribute("value") or "").strip()
            if desc_valor:
                logger.info(f"{label}: confirmado — descricao='{desc_valor}'")
            else:
                logger.warning(f"{label}: campo descricao vazio. Tentando Tab fallback...")
                self._tab_fallback(xpath_codigo, xpath_desc, codigo, label)
        except Exception:
            pass

        return True

    def _tab_fallback(
        self,
        xpath_codigo: str,
        xpath_desc: str,
        codigo: str,
        label: str,
    ) -> None:
        """
        Fallback: envia Tab key real pelo Selenium no campo de codigo
        para disparar o AJAX de validacao ASP.NET.
        Verifica se campo de descricao foi preenchido como confirmacao.
        """
        try:
            campo = self.driver.find_element(By.XPATH, xpath_codigo)
            self.driver.execute_script("arguments[0].value='';", campo)
            campo.send_keys(codigo)
            campo.send_keys(Keys.TAB)
            logger.debug(f"{label}: Tab key enviado para '{codigo}'.")
            time.sleep(2.5)
            _aguardar_carregamento(self.driver)

            # Verifica descricao
            try:
                desc_el = self.driver.find_element(By.XPATH, xpath_desc)
                desc_valor = (desc_el.get_attribute("value") or "").strip()
                if desc_valor:
                    logger.info(f"{label}: AJAX validou — descricao='{desc_valor}'")
                else:
                    logger.warning(f"{label}: descricao ainda vazia apos Tab key.")
            except Exception:
                pass
        except Exception as exc:
            logger.warning(f"{label}: Tab fallback falhou — {exc}")

    # ---------------------------------------------------------------------- #
    # RadDatePicker com XPath exato                                           #
    # ---------------------------------------------------------------------- #

    def _preencher_datepicker(self, xpath_input: str, id_input: str, data: str) -> bool:
        """
        Preenche RadDatePicker usando XPath exato para o campo visivel
        e ID exato para o ClientState JSON.
        Formato de entrada: DD/MM/AAAA.
        """
        try:
            partes = data.split("/")
            if len(partes) != 3:
                logger.warning(f"Data invalida: '{data}'. Use DD/MM/AAAA.")
                return False
            dia, mes, ano = partes
            data_iso = f"{ano}-{mes}-{dia}-00-00-00"
            id_cs = id_input + "_ClientState"

            client_state = (
                '{{"enabled":true,"emptyMessage":"","validationText":"{iso}",'
                '"valueAsString":"{iso}","minDateStr":"0001-01-01-00-00-00",'
                '"maxDateStr":"9999-12-31-00-00-00","lastSetTextBoxValue":"{dt}"}}'
            ).format(iso=data_iso, dt=data)

            # Preenche via XPath + send_keys real
            campo = WebDriverWait(self.driver, 8).until(
                EC.presence_of_element_located((By.XPATH, xpath_input))
            )
            self.driver.execute_script("arguments[0].value='';", campo)
            campo.send_keys(data)
            # Nao enviamos TAB aqui para evitar que o foco escape para
            # botoes do pager ou outros elementos interativos.
            # O ClientState e atualizado diretamente via JS logo abaixo.

            # Atualiza ClientState via ID exato
            self.driver.execute_script(
                """
                var cs=document.getElementById(arguments[0]);
                if(cs){cs.value=arguments[1];}
                """,
                id_cs, client_state,
            )
            logger.debug(f"DatePicker '{id_input}' preenchido com '{data}'.")
            return True
        except Exception as exc:
            logger.warning(f"Falha ao preencher DatePicker '{id_input}': {exc}")
            return False

    # ---------------------------------------------------------------------- #
    # Filtros                                                                 #
    # ---------------------------------------------------------------------- #

    def aplicar_filtros(self) -> None:
        """
        Fluxo v4.3 — preenche codigo+descricao diretamente via JS,
        desativa o validator do LOV e submete via postback direto.
        Isso garante que o grid receba a busca independente do AJAX de validacao.
        """
        logger.info("Aplicando filtros...")
        f = FILTROS

        # ── 1. Aba Historico ─────────────────────────────────────────────── #
        self.selecionar_aba_historico()
        time.sleep(1)

        # ── 2. Contratante: codigo + descricao via JS (sem depender do AJAX) ─ #
        # XPath codigo : //*[@id="ctl00_cphContext_tabManager_PV1_UC0_frvDocument_txbCompanyCode"]
        # XPath desc   : //*[@id="ctl00_cphContext_tabManager_PV1_UC0_frvDocument_txbCompanyDescription"]
        if f.get("contratante_codigo"):
            self.driver.execute_script(
                """
                var code = document.getElementById(arguments[0]);
                var desc = document.getElementById(arguments[1]);
                if (code) { code.value = arguments[2]; }
                if (desc) { desc.value = arguments[3]; }
                """,
                f"{_PV1}_txbCompanyCode",
                f"{_PV1}_txbCompanyDescription",
                f["contratante_codigo"],
                f.get("contratante_nome", ""),
            )
            logger.info(
                f"Contratante: '{f['contratante_codigo']}' / "
                f"'{f.get('contratante_nome','')}' preenchidos via JS."
            )

        # ── 3. Data De ────────────────────────────────────────────────────── #
        # XPath: //*[@id="ctl00_cphContext_tabManager_PV1_UC0_frvDocument_txbRemittanceDateFrom_dateInput"]
        if f.get("fechamento_de"):
            ok = self._preencher_datepicker(
                xpath_input=_XP["date_from"],
                id_input=_XP["date_from_input_id"],
                data=f["fechamento_de"],
            )
            logger.info(f"Data De '{f['fechamento_de']}': {'OK' if ok else 'FALHOU'}")

        # ── 4. Data Para ──────────────────────────────────────────────────── #
        # XPath: //*[@id="ctl00_cphContext_tabManager_PV1_UC0_frvDocument_txbRemittanceDateTo_dateInput"]
        if f.get("fechamento_ate"):
            ok = self._preencher_datepicker(
                xpath_input=_XP["date_to"],
                id_input=_XP["date_to_input_id"],
                data=f["fechamento_ate"],
            )
            logger.info(f"Data Para '{f['fechamento_ate']}': {'OK' if ok else 'FALHOU'}")

        # ── 5. Aguarda qualquer AJAX disparado pelo TAB no segundo datepicker ── #
        time.sleep(1)
        _aguardar_carregamento(self.driver)

        # ── 6. Desativa validators do grupo validateFilter ──────────────────── #
        # O cuvCompany exige txbCompanyDescription preenchido.
        # Como preenchemos ambos os campos via JS, desativamos o validator
        # para garantir que o postback nao seja bloqueado.
        self.driver.execute_script("""
            if (typeof Page_Validators !== 'undefined') {
                for (var i = 0; i < Page_Validators.length; i++) {
                    var v = Page_Validators[i];
                    if (!v.validationGroup || v.validationGroup === 'validateFilter') {
                        ValidatorEnable(v, false);
                    }
                }
            }
            // Garante Page_IsValid = true para o WebForm_DoPostBackWithOptions
            if (typeof Page_IsValid !== 'undefined') { Page_IsValid = true; }
        """)
        logger.debug("Validators do grupo validateFilter desativados.")

        # ── 7. Botao Buscar ───────────────────────────────────────────────── #
        # XPath: //*[@id="ctl00_cphContext_tabManager_PV1_UC0_frvDocument_btnFind"]
        try:
            btn_find = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, _XP["btn_find"]))
            )
            btn_find.click()
            logger.info("Botao Buscar clicado. Aguardando resultados...")
            time.sleep(6)
            _aguardar_carregamento(self.driver)
            self._diagnosticar_resultado()
        except Exception as exc:
            logger.error(f"Botao Buscar nao encontrado ou nao clicavel: {exc}")

    def _diagnosticar_resultado(self) -> None:
        """Loga informacoes sobre a grid de resultados para debug."""
        info = self.driver.execute_script("""
            var grid=document.querySelector("[id$='grdRemittance']");
            if(!grid) return {ok:false,msg:'grdRemittance nao encontrado'};
            var rows=grid.querySelectorAll('tr');
            var dados=0;
            for(var r=1;r<rows.length;r++){
                if(rows[r].querySelectorAll('td').length>=3) dados++;
            }
            return {ok:true,totalTr:rows.length,dados:dados,
                    preview:(grid.innerText||'').substring(0,300)};
        """)
        if info and info.get("ok"):
            logger.info(f"Grid resultado: {info['totalTr']} linhas tr, {info['dados']} com dados.")
            if info.get("preview"):
                logger.debug("Preview: " + info["preview"].replace("\n", " | ")[:250])
        else:
            msg = info.get("msg") if info else "None"
            logger.warning(f"Grid nao encontrado: {msg}")
            ids = self.driver.execute_script(
                "return Array.from(document.querySelectorAll('table'))"
                ".map(t=>t.id||'sem-id').slice(0,15);"
            )
            logger.debug(f"Tabelas presentes: {ids}")

    # ---------------------------------------------------------------------- #
    # Coleta e download paginado                                              #
    # ---------------------------------------------------------------------- #

    def coletar_e_processar_downloads(self, processador_callback) -> dict:
        resumo_total = {"ok": 0, "pulados": 0, "erros": 0, "total": 0}
        pagina = 1
        while True:
            # Log do indice real da pagina no grid Telerik (0-based)
            try:
                idx_real = self.driver.execute_script(
                    "var g=(typeof $find!=='undefined')?$find(arguments[0]):null;"
                    "return g?g.get_masterTableView().get_currentPageIndex():'?';",
                    _GRID_ID,
                )
            except Exception:
                idx_real = "?"
            logger.info(f"Processando pagina {pagina} (grid index={idx_real})...")
            linhas = coletar_linhas_pagina(self.driver)
            if not linhas:
                logger.info("Nenhuma linha encontrada — encerrando paginacao.")
                break
            resumo_pg = processador_callback(self.driver, linhas)
            resumo_total["ok"]      += resumo_pg["ok"]
            resumo_total["pulados"] += resumo_pg["pulados"]
            resumo_total["erros"]   += resumo_pg["erros"]
            resumo_total["total"]   += resumo_pg["total"]
            tem_prox = tem_proxima_pagina(self.driver, pagina)
            logger.info(
                f"Pagina {pagina} concluida — "
                f"ok={resumo_pg['ok']} | pulados={resumo_pg['pulados']} | "
                f"erros={resumo_pg['erros']} | tem_proxima={tem_prox}"
            )
            if tem_prox:
                ir_proxima_pagina(self.driver)
                pagina += 1
            else:
                logger.info("Ultima pagina atingida — encerrando paginacao.")
                break
        return resumo_total


# --------------------------------------------------------------------------- #
# Diagnostico                                                                  #
# --------------------------------------------------------------------------- #

def diagnosticar_campos(driver: webdriver.Chrome) -> None:
    logger.debug("=== DIAGNOSTICO DE CAMPOS ===")
    for el in driver.find_elements(By.CSS_SELECTOR, "input, select, textarea"):
        logger.debug(
            "  tag=%-8s id=%-50s name=%-40s type=%-10s value=%r" % (
                el.tag_name,
                el.get_attribute("id") or "",
                el.get_attribute("name") or "",
                el.get_attribute("type") or "",
                el.get_attribute("value"),
            )
        )
    logger.debug("=== FIM DO DIAGNOSTICO ===")


# --------------------------------------------------------------------------- #
# Helpers standalone                                                           #
# --------------------------------------------------------------------------- #

def _encontrar_campo(driver: webdriver.Chrome, seletores: list):
    for seletor in seletores:
        try:
            el = driver.find_element(By.CSS_SELECTOR, seletor)
            if el:
                return el
        except Exception:
            continue
    return None


def _preencher_simples(driver: webdriver.Chrome, seletores: list, valor: str) -> bool:
    campo = _encontrar_campo(driver, seletores)
    if campo:
        campo.clear()
        campo.send_keys(valor)
        return True
    return False


def _preencher_lookup(driver: webdriver.Chrome, seletores_codigo: list, codigo: str) -> bool:
    campo = _encontrar_campo(driver, seletores_codigo)
    if campo is None:
        return False
    campo.clear()
    campo.send_keys(codigo)
    campo.send_keys(Keys.TAB)
    time.sleep(2)
    _aguardar_carregamento(driver)
    return True


def _preencher_rad_datepicker(driver: webdriver.Chrome, id_date_input: str, data: str) -> bool:
    try:
        partes = data.split("/")
        if len(partes) != 3:
            return False
        dia, mes, ano = partes
        data_iso = f"{ano}-{mes}-{dia}-00-00-00"
        id_cs = id_date_input + "_ClientState"
        cs_val = (
            '{{"enabled":true,"emptyMessage":"","validationText":"{iso}",'
            '"valueAsString":"{iso}","minDateStr":"0001-01-01-00-00-00",'
            '"maxDateStr":"9999-12-31-00-00-00","lastSetTextBoxValue":"{dt}"}}'
        ).format(iso=data_iso, dt=data)
        driver.execute_script(
            """
            var inp=document.getElementById(arguments[0]);
            if(inp){inp.value=arguments[2];
                inp.dispatchEvent(new Event('change',{bubbles:true}));
                inp.dispatchEvent(new Event('blur',{bubbles:true}));}
            var cs=document.getElementById(arguments[1]);
            if(cs){cs.value=arguments[3];}
            """,
            id_date_input, id_cs, data, cs_val,
        )
        time.sleep(0.5)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Paginacao e coleta                                                           #
# --------------------------------------------------------------------------- #

def ajustar_paginacao(driver: webdriver.Chrome) -> None:
    try:
        sel_el = driver.find_element(
            By.CSS_SELECTOR,
            "select[id*='PageSize'],select[name*='PageSize'],"
            "select[id*='registros'],select[id*='Pagina']",
        )
        sel = Select(sel_el)
        try:
            sel.select_by_value(str(ROWS_PER_PAGE))
        except Exception:
            sel.select_by_visible_text(str(ROWS_PER_PAGE))
        time.sleep(2)
        logger.info(f"Paginacao: {ROWS_PER_PAGE} linhas/pagina.")
    except Exception:
        logger.debug("Dropdown de paginacao nao encontrado.")


def coletar_linhas_pagina(driver: webdriver.Chrome) -> list:
    """
    Le linhas do grid de resultados (grdRemittance) via CSS selector robusto.

    Mapeamento de colunas confirmado (FAS903 - aba Historico):
      idx 0 = Remessa
      idx 1 = Arquivo
      idx 2 = btnDetails (input.btnGrid.btnDetails, title='Visualizar Documentos')
      idx 3 = Contratante
      idx 4 = Cedente
      idx 5 = btnZip  (Baixar arquivo Zip)
      idx 6 = btnXml  (Baixar arquivo Xml)
      idx 7 = Tit.Neces
      idx 8 = Tit.Atu
      idx 9 = Recebimento
      idx 10 = Fechamento
      idx 11 = (vazio)
    """
    linhas = []

    # CSS selector direto nas linhas de dados — ignora headers e containers
    rows = driver.find_elements(By.CSS_SELECTOR, "tr[id*='grdRemittance_ctl00__']")
    if not rows:
        logger.warning("  Nenhuma linha encontrada pelo CSS selector grdRemittance_ctl00__")
        return linhas

    for row in rows:
        cols = row.find_elements(By.TAG_NAME, "td")
        if len(cols) < 5:
            continue
        try:
            remessa     = cols[0].text.strip()
            arquivo     = cols[1].text.strip()
            contratante = cols[3].text.strip()
            cedente     = cols[4].text.strip()
            tit_neces   = cols[7].text.strip()  if len(cols) > 7  else ""
            tit_atu     = cols[8].text.strip()  if len(cols) > 8  else ""
            recebimento = cols[9].text.strip()  if len(cols) > 9  else ""
            fechamento  = cols[10].text.strip() if len(cols) > 10 else ""

            if not remessa and not arquivo:
                continue

            # idx 2 = btnDetails — input[type=submit] que abre popup "Documentos da remessa"
            icone_doc = None
            try:
                icone_doc = cols[2].find_element(By.CSS_SELECTOR, "input.btnDetails")
            except Exception:
                pass
            if icone_doc is None:
                for tag in ("input", "a", "button", "img"):
                    c = cols[2].find_elements(By.TAG_NAME, tag)
                    if c:
                        icone_doc = c[0]
                        break
            if icone_doc is None:
                icone_doc = cols[2]  # fallback: o proprio td

            row_id = row.get_attribute("id") or ""

            linhas.append({
                "remessa": remessa, "arquivo": arquivo,
                "contratante": contratante, "cedente": cedente,
                "tit_neces": tit_neces, "tit_atu": tit_atu,
                "recebimento": recebimento, "fechamento": fechamento,
                "elemento_download": icone_doc,
                "row_element": row,
                "row_id": row_id,   # usado para re-localizar apos stale element
            })
        except Exception as exc:
            logger.debug(f"Erro na linha: {exc}")
            continue

    logger.info(f"  {len(linhas)} linhas coletadas nesta pagina.")
    return linhas


def _total_paginas(driver: webdriver.Chrome) -> int:
    """Retorna o total de paginas do grdRemittance via Telerik API. 0 = desconhecido."""
    try:
        total = driver.execute_script(
            "var g=$find(arguments[0]); return g ? g.get_masterTableView().get_pageCount() : 0;",
            _GRID_ID,
        )
        return int(total) if total else 0
    except Exception:
        return 0



def tem_proxima_pagina(driver: webdriver.Chrome, pagina_atual: int = 1) -> bool:
    """
    Verifica se existe proxima pagina usando o botao Next Page do pager.
    XPath confirmado em inspecao DOM:
      _XPATH_NEXT_PAGE = .../div[3]/input[1]
    O botao e um input[type=submit]; disabled=True indica ultima pagina.
    """
    # Estrategia 1: Telerik RadGrid JS API — mais confiavel quando disponivel
    try:
        total = _total_paginas(driver)
        if total > 0:
            logger.debug(f"Paginacao via API: pagina {pagina_atual} de {total}.")
            return pagina_atual < total
    except Exception:
        pass

    # Estrategia 2: XPath exato do botao input "Next Page" no pager
    try:
        els = driver.find_elements(By.XPATH, _XPATH_NEXT_PAGE)
        if not els:
            return False
        btn = els[0]
        habilitado = btn.is_enabled()
        logger.debug(f"Botao Next Page: is_enabled={habilitado}")
        return habilitado
    except Exception:
        return False


def ir_proxima_pagina(driver: webdriver.Chrome) -> None:
    """
    Clica no botao Next Page do pager do grid grdRemittance.
    XPath confirmado: _XPATH_NEXT_PAGE (.../div[3]/input[1])
    """
    try:
        els = driver.find_elements(By.XPATH, _XPATH_NEXT_PAGE)
        if not els:
            logger.warning("Botao Next Page nao encontrado via XPath — tentando JS API.")
            # Fallback: Telerik JS API
            driver.execute_script(
                """
                var g = (typeof $find !== 'undefined') ? $find(arguments[0]) : null;
                if (g) {
                    var mtv = g.get_masterTableView();
                    mtv.page(mtv.get_currentPageIndex() + 1);
                }
                """,
                _GRID_ID,
            )
        else:
            btn = els[0]
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            btn.click()
            logger.info("Botao Next Page clicado via XPath. Aguardando grid atualizar...")

        time.sleep(4)
        _aguardar_carregamento(driver)

    except Exception as exc:
        logger.warning(f"Erro ao ir para proxima pagina: {exc}")
