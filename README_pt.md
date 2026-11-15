[简体中文](README.md) | [繁體中文](README_zh_TW.md) | [English](README_EN.md) | [日本語](README_ja.md) | [한국어](README_ko.md) | [Deutsch](README_de.md) | [Français](README_fr.md) | [Español](README_es.md) | [Русский](README_ru.md) | [**Português**](README_pt.md)

# lspy

> Uma implementação de linha de comando do protocolo LocalSend. Arquivo único, sem dependências de terceiros: LocalSend no celular, um comando no computador. Inclui retransmissão entre redes via ntfy.sh.

[![CI](https://github.com/styisme/lspy/actions/workflows/ci.yml/badge.svg)](https://github.com/styisme/lspy/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.27.2-512BD4)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Made with AI](https://img.shields.io/badge/made%20with-AI-FF6B6B)](docs/AI_DISCLOSURE.md)

---

## ⚠️ Divulgação de geração por IA

Este projeto foi amplamente desenvolvido com auxílio de modelos de linguagem. Requisitos, revisão, verificação e publicação são de responsabilidade humana. Detalhes em [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md); o projeto segue as [AI Development Guidelines](https://github.com/styisme/ai-development-guidelines).

---

## ✨ Principais recursos

- **Duas gerações de protocolo**: LocalSend `v2` (`prepare-upload`/`upload`/`cancel`) e `v2.1` (`send-request`/`send`); o prefixo `v1` também funciona. Fallback automático em 404/405.
- **Descoberta tripla**: multicast `224.0.0.167:53317`, broadcast de sub-rede e **varredura HTTP profunda** (todas as interfaces, duas portas em paralelo).
- **Retomada sem sobrescrever**: continua a partir do deslocamento em disco; nomes passam por `safe_filename` + `unique_path`, conflitos viram `(1)`.
- **Controle de acesso**: PIN (`401` + `X-LocalSend-Pin`), listas branca/negra de impressões digitais, filtro de extensões perigosas (ignoradas por arquivo).
- **Proteção Zip Slip**: caminhos absolutos, letras de unidade, travessia `..` e links simbólicos são recusados.
- **TLS**: `lspy cert` gera um par autoassinado; ambos os lados podem usar HTTPS.
- **Entre redes**: via ntfy.sh, blocos de 2400 bytes, 3 tentativas, SHA-256 final.
- **Página web de partilha** (envio / descarga / texto, portada do watchsend; a página segue o `Accept-Language` do navegador), **10 idiomas de interface**.
- **Histórico e depuração** (também do watchsend): `history --delete N` / `--clear` / `--unzip N` (ZIP marcado 📦, proteção Zip Slip), `--debug-keys` mostra as chaves i18n em bruto.
- **Detalhes na receção**: `.txt` recebidos até 10 KB vão direto para a área de transferência (desativável com `clipboard_text`), o histórico é limitado por `history_max` (300 por predefinição) e `info` mostra ainda `[IPv6]:porta`.
- **Seleção de ficheiros sem tkinter**: o [cfdialog](https://github.com/styisme/cfdialog) 0.3.0 incluído (MIT, ficheiro único) substitui a caixa tkinter por um navegador de terminal (números, `g` partições, `h` ocultos, `a`/`c`/`d` seleção múltipla); `?` na pasta de receção abre o navegador de pastas. `config --set force_cfdialog=true` força o navegador de terminal e ignora o tkinter. No Android o tkinter é ignorado (raramente inclui Tk) e o navegador arranca de imediato.

---
- **Receber de qualquer tela**: todo ponto de entrada (menu, ajustes, selecao de arquivos) monitora a fila de transferencias recebidas e mostra o pedido de aceitacao na hora. Com `auto_accept` ligado, vai direto ao detalhe de recebimento; depois, Enter volta a tela anterior.
- **Permanecer apos o envio**: um envio concluido nao some mais - Enter volta ao menu.

## 📱 Início rápido

```bash
git clone https://github.com/styisme/lspy.git
cd lspy
python lspy.py --help          # sem instalar
pip install .                  # instala o comando `lspy`

lspy serve --web
lspy scan
lspy send a.jpg --ip 192.168.1.20:53317 --pin 1234
lspy cross-send photo.zip
```

Python 3.8+, sem dependências. Libere TCP/UDP `53317`.

---

## 🛠️ Compilação e testes

```bash
pip install .
python -m unittest discover -s tests -v
python scripts/sync_version.py --check
pip install pyinstaller && python scripts/build_binary.py
```

Sem Python: use o binário autônomo de [Releases](https://github.com/styisme/lspy/releases) — Windows `lspy-<versão>-windows-x64.exe`, Linux `lspy-<versão>-linux-x86_64`.

Um push de `CHANGELOG.md` para `main` compila os binários em Windows e Linux e publica automaticamente a tag e o Release com o wheel e o sdist.


---

## 🚧 Riscos e limitações

1. **Alta participação de IA**: protocolo, verificações de segurança e scripts de CI são assistidos por IA; revisão humana e testes reais são obrigatórios. Não é uma implementação auditada.
2. **Canal entre redes em texto claro**: o tópico ntfy é o PIN — PIN vazado, arquivo vazado. Não envie dados sensíveis.
3. **Arquitetura de arquivo único**: `lspy.py` tem cerca de 1500 linhas; fácil de distribuir, fraco em modularidade e análise estática.
4. **TLS autoassinado**: cadeias de certificados não são validadas, sem proteção contra MITM.

---

## 📜 Licença

MIT ([LICENSE](LICENSE)). Aviso de compatibilidade: [LICENSE-LocalSend](LICENSE-LocalSend).
