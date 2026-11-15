[简体中文](README.md) | [繁體中文](README_zh_TW.md) | [English](README_EN.md) | [日本語](README_ja.md) | [한국어](README_ko.md) | [Deutsch](README_de.md) | [**Français**](README_fr.md) | [Español](README_es.md) | [Русский](README_ru.md) | [Português](README_pt.md)

# lspy

> Une implémentation en ligne de commande du protocole LocalSend. Un seul fichier, aucune dépendance tierce : LocalSend sur le téléphone, une commande sur l'ordinateur. Relais inter-réseaux via ntfy.sh inclus.

[![CI](https://github.com/styisme/lspy/actions/workflows/ci.yml/badge.svg)](https://github.com/styisme/lspy/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.24.0-512BD4)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Made with AI](https://img.shields.io/badge/made%20with-AI-FF6B6B)](docs/AI_DISCLOSURE.md)

---

## ⚠️ Divulgation de génération par IA

Ce projet a été largement développé avec l'aide de modèles de langage. Les exigences, la revue, la vérification et la publication restent humaines. Détails dans [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md) ; le projet suit les [AI Development Guidelines](https://github.com/styisme/ai-development-guidelines).

---

## ✨ Fonctionnalités principales

- **Deux générations de protocole** : LocalSend `v2` (`prepare-upload`/`upload`/`cancel`) et `v2.1` (`send-request`/`send`) ; le préfixe `v1` fonctionne aussi. Repli automatique sur 404/405.
- **Découverte triple** : multicast `224.0.0.167:53317`, diffusion de sous-réseau et **scan HTTP approfondi** (toutes les interfaces, deux ports en parallèle).
- **Reprise sans écrasement** : reprise depuis l'offset sur disque ; les noms passent par `safe_filename` + `unique_path`, les conflits deviennent `(1)`.
- **Contrôle d'accès** : PIN (`401` + `X-LocalSend-Pin`), listes blanche/noire d'empreintes, filtre d'extensions dangereuses (ignorées fichier par fichier).
- **Protection Zip Slip** : chemins absolus, lettres de lecteur, traversée `..` et liens symboliques refusés.
- **TLS** : `lspy cert` génère une paire auto-signée ; les deux côtés peuvent utiliser HTTPS.
- **Inter-réseaux** : via ntfy.sh, blocs de 2400 octets, 3 tentatives, empreinte SHA-256 finale.
- **Page de partage web** (envoi / téléchargement / texte, portée depuis watchsend ; la page suit l'`Accept-Language` du navigateur), **10 langues d'interface**.
- **Historique & debug** (également issus de watchsend) : `history --delete N` / `--clear` / `--unzip N` (ZIP marqué 📦, protection Zip Slip), `--debug-keys` affiche les clés i18n brutes.
- **Petits plus à la réception** : les `.txt` reçus jusqu'à 10 Ko partent automatiquement dans le presse-papiers (désactivable via `clipboard_text`), l'historique est plafonné par `history_max` (300 par défaut), et `info` affiche aussi `[IPv6]:port`.
- **Sélecteur de fichiers sans tkinter** : [cfdialog](https://github.com/styisme/cfdialog) 0.3.0 embarqué (MIT, un seul fichier) remplace la boîte tkinter par un navigateur terminal (numéros, `g` partitions, `h` fichiers cachés, `a`/`c`/`d` sélection multiple) ; `?` sur le dossier de réception ouvre l'explorateur de dossiers.

---

## 📱 Démarrage rapide

```bash
git clone https://github.com/styisme/lspy.git
cd lspy
python lspy.py --help          # sans installation
pip install .                  # installer la commande `lspy`

lspy serve --web
lspy scan
lspy send a.jpg --ip 192.168.1.20:53317 --pin 1234
lspy cross-send photo.zip
```

Python 3.8+, aucune dépendance. Autorisez TCP/UDP `53317`.

---

## 🛠️ Compilation et tests

```bash
pip install .
python -m unittest discover -s tests -v
python scripts/sync_version.py --check
pip install pyinstaller && python scripts/build_binary.py
```

Sans Python : le binaire autonome des [Releases](https://github.com/styisme/lspy/releases) — Windows `lspy-<version>-windows-x64.exe`, Linux `lspy-<version>-linux-x86_64`.

Un push de `CHANGELOG.md` sur `main` compile les binaires sous Windows et Linux, puis tague et publie automatiquement avec le wheel et le sdist.


---

## 🚧 Risques et limites

1. **Forte implication de l'IA** : protocole, contrôles de sécurité et scripts CI sont assistés par IA ; revue humaine et essais réels obligatoires. Ce n'est pas une implémentation auditée.
2. **Canal inter-réseaux en clair** : le sujet ntfy est le PIN — PIN fuité, fichier fuité. N'envoyez pas de données sensibles.
3. **Architecture mono-fichier** : `lspy.py` fait environ 1500 lignes ; facile à distribuer, faible en modularité et analyse statique.
4. **TLS auto-signé** : les chaînes ne sont pas vérifiées, donc aucune protection contre un MITM.

---

## 📜 Licence

MIT ([LICENSE](LICENSE)). Compatibilité protocole : [LICENSE-LocalSend](LICENSE-LocalSend).
