# Q-Certifica — Downloader Automático de Contratos

Automação de download em massa de contratos PDF a partir do portal [Q-Certifica](https://portal.qcertifica.com.br), eliminando a necessidade de interação manual com a interface web.

## Visão Geral

O portal Q-Certifica não oferece download em lote. Para um lote típico de 163 documentos em 120 dias, o processo manual consome ~97 minutos de atenção contínua. Esta automação executa o mesmo pipeline em ~20 minutos de forma **desassistida**, representando um saving de **R$ 47,50 por lote** (base: R$ 30,00/hora).

## Funcionalidades

- Interface gráfica desktop (tkinter) com campos de credencial, filtros e log em tempo real
- Login automático com tratamento do popup de sessão duplicada
- Preenchimento de filtros via Selenium + JavaScript (Telerik RadGrid/RadDatePicker)
- Paginação automática por todas as páginas do grid
- Download individual via modal com retry automático (3 tentativas)
- Checkpoint de retomada — nunca baixa o mesmo arquivo duas vezes
- Log de auditoria em CSV com status de cada operação
- Regra de intervalo máximo de 120 dias com validação em tempo real
- Executável `.exe` standalone via PyInstaller

## Pré-requisitos

- Python 3.10+
- Google Chrome instalado
- Conexão com a internet (para download automático do ChromeDriver)

## Instalação

```bash
git clone https://github.com/cdsnascimento/_projeto_rpa_qcertifica.git
cd _projeto_rpa_qcertifica/qcertifica_scraper
pip install selenium webdriver-manager python-dotenv tkcalendar
```

## Uso

### Interface Gráfica (recomendado)

```bash
python app.py
```

Preencha os campos e clique em **Iniciar**. Os downloads serão salvos na pasta `downloads/`.

### Linha de Comando

```bash
# Configure as credenciais como variáveis de ambiente
set QCERTIFICA_USER=seu_cpf
set QCERTIFICA_PASS=sua_senha

python main.py
```

## Gerar Executável

```bash
build.bat
```

O arquivo `dist\QCertifica.exe` será gerado pronto para uso, sem necessidade de instalação do Python.

## Estrutura do Projeto

```
qcertifica_scraper/
├── app.py               # Interface gráfica (ponto de entrada principal)
├── scraper.py           # Motor de automação Selenium
├── downloader.py        # Download via modal PDF
├── config.py            # Configurações e filtros
├── utils.py             # Logger, checkpoint, utilitários
├── main.py              # Entry point via linha de comando
├── qcertifica.spec      # Spec do PyInstaller
├── build.bat            # Script de build do executável
├── downloads/           # PDFs baixados (gerado automaticamente)
├── checkpoint.txt       # Controle de arquivos já baixados
└── downloads_log.csv    # Auditoria de downloads
```

## Configuração

Edite `config.py` para ajustar filtros padrão, timeouts e comportamento. Ao usar a interface gráfica, os valores são sobrescritos em tempo de execução sem necessidade de editar o arquivo.

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `HEADLESS` | `False` | `True` = Chrome sem janela |
| `DOWNLOAD_WAIT` | `15s` | Timeout por PDF |
| `PAGE_LOAD_TIMEOUT` | `30s` | Timeout de página |

## Segurança

As credenciais são injetadas via `os.environ` em tempo de execução e nunca gravadas em disco. O arquivo `.env` (se utilizado localmente) está no `.gitignore` e jamais deve ser commitado.

## Tecnologias

Python · Selenium · webdriver-manager · tkinter · tkcalendar · PyInstaller
