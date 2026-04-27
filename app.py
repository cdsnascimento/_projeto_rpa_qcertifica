# app.py — Interface gráfica para o scraper Q-Certifica
#
# Executa o pipeline completo em thread de fundo enquanto exibe logs em tempo real.
# Credenciais são passadas via os.environ (sem gravar em disco).
# Filtros substituem config.FILTROS antes de chamar o scraper.

import logging
import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, scrolledtext, ttk

# ---------------------------------------------------------------------------
# Tenta importar tkcalendar; se não disponível usa Entry simples com hint
# ---------------------------------------------------------------------------
try:
    from tkcalendar import DateEntry
    _HAS_TKCALENDAR = True
except ImportError:
    _HAS_TKCALENDAR = False

_MAX_DIAS = 120
_DATE_FMT = "%d/%m/%Y"


# ---------------------------------------------------------------------------
# Handler de logging que redireciona para o widget de texto da GUI
# ---------------------------------------------------------------------------
class _TextHandler(logging.Handler):
    def __init__(self, widget: scrolledtext.ScrolledText):
        super().__init__()
        self._widget = widget

    def emit(self, record: logging.LogRecord):
        msg = self.format(record) + "\n"
        # tkinter não é thread-safe; usa after() para atualizar na thread principal
        self._widget.after(0, self._append, msg)

    def _append(self, msg: str):
        self._widget.configure(state="normal")
        self._widget.insert(tk.END, msg)
        self._widget.see(tk.END)
        self._widget.configure(state="disabled")


# ---------------------------------------------------------------------------
# Janela principal
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Q-Certifica — Downloader de Contratos")
        self.resizable(True, True)
        self.minsize(640, 540)

        self._build_ui()
        self._thread: threading.Thread | None = None

        # Calcula o intervalo inicial (valores default já preenchidos)
        self._atualizar_intervalo()

    # ------------------------------------------------------------------
    # Construção da interface
    # ------------------------------------------------------------------
    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        # ── Quadro de credenciais ──────────────────────────────────────
        frm_cred = ttk.LabelFrame(self, text="Credenciais")
        frm_cred.grid(row=0, column=0, sticky="ew", **pad)
        self.columnconfigure(0, weight=1)

        ttk.Label(frm_cred, text="Usuário:").grid(row=0, column=0, sticky="e", padx=6, pady=4)
        self._var_usuario = tk.StringVar(value=os.environ.get("QCERTIFICA_USER", ""))
        self._ent_usuario = ttk.Entry(frm_cred, textvariable=self._var_usuario, width=30)
        self._ent_usuario.grid(row=0, column=1, sticky="w", padx=6, pady=4)

        ttk.Label(frm_cred, text="Senha:").grid(row=1, column=0, sticky="e", padx=6, pady=4)
        self._var_senha = tk.StringVar(value=os.environ.get("QCERTIFICA_PASS", ""))
        self._ent_senha = ttk.Entry(frm_cred, textvariable=self._var_senha, show="*", width=30)
        self._ent_senha.grid(row=1, column=1, sticky="w", padx=6, pady=4)

        # ── Quadro de filtros ─────────────────────────────────────────
        frm_filt = ttk.LabelFrame(self, text="Filtros de Busca")
        frm_filt.grid(row=1, column=0, sticky="ew", **pad)

        ttk.Label(frm_filt, text="Cód. Contratante:").grid(row=0, column=0, sticky="e", padx=6, pady=4)
        self._var_contratante = tk.StringVar(value="67632")
        self._ent_contratante = ttk.Entry(frm_filt, textvariable=self._var_contratante, width=18)
        self._ent_contratante.grid(row=0, column=1, sticky="w", padx=6, pady=4)

        # Data De
        ttk.Label(frm_filt, text="Data De:").grid(row=1, column=0, sticky="e", padx=6, pady=4)
        self._var_de = tk.StringVar(value="01/01/2022")
        self._var_de.trace_add("write", lambda *_: self._atualizar_intervalo())
        self._ent_de = self._make_datepicker(frm_filt, self._var_de)
        self._ent_de.grid(row=1, column=1, sticky="w", padx=6, pady=4)

        # Data Até
        ttk.Label(frm_filt, text="Data Até:").grid(row=2, column=0, sticky="e", padx=6, pady=4)
        self._var_ate = tk.StringVar(value="30/04/2022")
        self._var_ate.trace_add("write", lambda *_: self._atualizar_intervalo())
        self._ent_ate = self._make_datepicker(frm_filt, self._var_ate)
        self._ent_ate.grid(row=2, column=1, sticky="w", padx=6, pady=4)

        # Diferença em dias (somente leitura)
        ttk.Label(frm_filt, text="Intervalo:").grid(row=3, column=0, sticky="e", padx=6, pady=4)
        frm_intervalo = ttk.Frame(frm_filt)
        frm_intervalo.grid(row=3, column=1, sticky="w", padx=6, pady=4)

        self._var_dias = tk.StringVar(value="—")
        self._lbl_dias = ttk.Entry(
            frm_intervalo,
            textvariable=self._var_dias,
            width=6,
            state="readonly",
            justify="center",
            font=("Segoe UI", 9, "bold"),
        )
        self._lbl_dias.pack(side="left")
        ttk.Label(frm_intervalo, text="dias").pack(side="left", padx=(4, 0))

        # Aviso de limite (inicialmente oculto)
        self._lbl_aviso = ttk.Label(
            frm_filt,
            text=f"⚠  Intervalo máximo permitido: {_MAX_DIAS} dias.",
            foreground="#c0392b",
        )
        # posicionado na row 4, coluna 0-1 — exibido apenas quando necessário
        self._aviso_visivel = False

        # ── Botão Iniciar ─────────────────────────────────────────────
        self._btn_iniciar = ttk.Button(
            self, text="▶  Iniciar", command=self._iniciar
        )
        self._btn_iniciar.grid(row=2, column=0, pady=(4, 10))

        # ── Área de log ───────────────────────────────────────────────
        frm_log = ttk.LabelFrame(self, text="Log de execução")
        frm_log.grid(row=3, column=0, sticky="nsew", **pad)
        self.rowconfigure(3, weight=1)

        self._log_area = scrolledtext.ScrolledText(
            frm_log,
            height=18,
            state="disabled",
            font=("Consolas", 9),
            wrap=tk.WORD,
        )
        self._log_area.pack(fill="both", expand=True, padx=4, pady=4)

        # ── Barra de status ───────────────────────────────────────────
        self._status_var = tk.StringVar(value="Pronto.")
        ttk.Label(self, textvariable=self._status_var, anchor="w").grid(
            row=4, column=0, sticky="ew", padx=10, pady=(0, 6)
        )

    # ------------------------------------------------------------------
    # Cria campo de data (DateEntry ou Entry simples)
    # ------------------------------------------------------------------
    def _make_datepicker(self, parent, textvariable: tk.StringVar):
        if _HAS_TKCALENDAR:
            w = DateEntry(
                parent,
                textvariable=textvariable,
                date_pattern="dd/MM/yyyy",
                width=14,
                background="#2b5dbd",
                foreground="white",
                borderwidth=2,
            )
            return w
        else:
            ent = ttk.Entry(parent, textvariable=textvariable, width=16)
            return ent

    # ------------------------------------------------------------------
    # Calcula e exibe a diferença em dias; habilita/desabilita o botão
    # ------------------------------------------------------------------
    def _atualizar_intervalo(self):
        de_str  = self._var_de.get().strip()
        ate_str = self._var_ate.get().strip()

        try:
            d_de  = datetime.strptime(de_str,  _DATE_FMT)
            d_ate = datetime.strptime(ate_str, _DATE_FMT)
            dias  = (d_ate - d_de).days
        except ValueError:
            # Data incompleta ou inválida — não calcula ainda
            self._var_dias.set("—")
            self._set_aviso(False)
            self._btn_iniciar.configure(state="normal")
            return

        if dias < 0:
            self._var_dias.set("—")
            self._set_aviso(False)
            self._btn_iniciar.configure(state="normal")
            return

        self._var_dias.set(str(dias))

        if dias > _MAX_DIAS:
            self._set_aviso(True)
            self._btn_iniciar.configure(state="disabled")
            self._status_var.set(
                f"⚠  Intervalo de {dias} dias excede o limite de {_MAX_DIAS} dias."
            )
        else:
            self._set_aviso(False)
            self._btn_iniciar.configure(state="normal")
            self._status_var.set("Pronto.")

    # ------------------------------------------------------------------
    # Exibe ou oculta o label de aviso dentro do quadro de filtros
    # ------------------------------------------------------------------
    def _set_aviso(self, visivel: bool):
        if visivel and not self._aviso_visivel:
            self._lbl_aviso.grid(
                row=4, column=0, columnspan=2,
                sticky="w", padx=6, pady=(0, 4)
            )
            self._aviso_visivel = True
        elif not visivel and self._aviso_visivel:
            self._lbl_aviso.grid_remove()
            self._aviso_visivel = False

    # ------------------------------------------------------------------
    # Validação dos campos
    # ------------------------------------------------------------------
    def _validar(self) -> bool:
        erros = []
        if not self._var_usuario.get().strip():
            erros.append("• Usuário é obrigatório.")
        if not self._var_senha.get().strip():
            erros.append("• Senha é obrigatória.")
        if not self._var_contratante.get().strip():
            erros.append("• Código do Contratante é obrigatório.")
        if not self._var_de.get().strip():
            erros.append("• Data De é obrigatória.")
        if not self._var_ate.get().strip():
            erros.append("• Data Até é obrigatória.")
        if erros:
            messagebox.showerror("Campos obrigatórios", "\n".join(erros))
            return False
        return True

    # ------------------------------------------------------------------
    # Configuração do logging antes de rodar
    # ------------------------------------------------------------------
    def _configurar_logging(self):
        handler = _TextHandler(self._log_area)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        root_log = logging.getLogger()
        # Remove handlers antigos de arquivo para não duplicar
        root_log.handlers = [
            h for h in root_log.handlers
            if not isinstance(h, logging.FileHandler)
        ]
        root_log.addHandler(handler)
        root_log.setLevel(logging.DEBUG)

    # ------------------------------------------------------------------
    # Inicia o scraper em thread de fundo
    # ------------------------------------------------------------------
    def _iniciar(self):
        if not self._validar():
            return
        if self._thread and self._thread.is_alive():
            messagebox.showinfo("Em execução", "O processo já está rodando.")
            return

        # Injeta credenciais em variáveis de ambiente
        os.environ["QCERTIFICA_USER"] = self._var_usuario.get().strip()
        os.environ["QCERTIFICA_PASS"] = self._var_senha.get().strip()

        # Atualiza filtros globais em config
        import config
        config.FILTROS["contratante_codigo"] = self._var_contratante.get().strip()
        config.FILTROS["fechamento_de"]       = self._var_de.get().strip()
        config.FILTROS["fechamento_ate"]      = self._var_ate.get().strip()

        self._configurar_logging()
        self._set_form_state("disabled")
        self._status_var.set("Executando…")

        self._thread = threading.Thread(target=self._executar, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # Rotina principal do scraper (roda na thread de fundo)
    # ------------------------------------------------------------------
    def _executar(self):
        log = logging.getLogger(__name__)
        driver = None
        try:
            from utils import init_log
            init_log()

            from scraper import create_driver, QCertificaScraper
            from downloader import processar_downloads

            driver = create_driver()
            s = QCertificaScraper(driver)
            s.login()
            s.navegar_fas903()
            s.aplicar_filtros()
            resumo = s.coletar_e_processar_downloads(processar_downloads)

            log.info("=" * 60)
            log.info("Processo concluído.")
            if resumo:
                log.info(
                    "Total: %d | Baixados: %d | Pulados: %d | Erros: %d",
                    resumo.get("total", 0),
                    resumo.get("ok", 0),
                    resumo.get("pulados", 0),
                    resumo.get("erros", 0),
                )
            self.after(0, self._status_var.set, "Concluído ✔")

        except Exception as exc:
            log.exception("Erro fatal durante a execução: %s", exc)
            self.after(0, self._status_var.set, f"Erro: {exc}")
            self.after(0, messagebox.showerror, "Erro", str(exc))
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
            self.after(0, self._set_form_state, "normal")

    # ------------------------------------------------------------------
    # Habilita / desabilita todos os campos do formulário
    # ------------------------------------------------------------------
    def _set_form_state(self, state: str):
        widgets = [
            self._ent_usuario,
            self._ent_senha,
            self._ent_contratante,
            self._ent_de,
            self._ent_ate,
        ]
        for w in widgets:
            try:
                w.configure(state=state)
            except tk.TclError:
                pass

        # O botão Iniciar só volta a "normal" se o intervalo ainda for válido
        if state == "normal":
            self._atualizar_intervalo()
        else:
            self._btn_iniciar.configure(state=state)


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = App()
    app.mainloop()
