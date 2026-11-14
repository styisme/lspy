[简体中文](README.md) | [繁體中文](README_zh_TW.md) | [English](README_EN.md) | [日本語](README_ja.md) | [한국어](README_ko.md) | [Deutsch](README_de.md) | [Français](README_fr.md) | [Español](README_es.md) | [**Русский**](README_ru.md) | [Português](README_pt.md)

# lspy

> Реализация протокола LocalSend в командной строке. Один файл, без сторонних зависимостей: LocalSend на телефоне, одна команда на компьютере. Есть ретрансляция между сетями через ntfy.sh.

[![CI](https://github.com/styisme/lspy/actions/workflows/ci.yml/badge.svg)](https://github.com/styisme/lspy/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.19.2-512BD4)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Made with AI](https://img.shields.io/badge/made%20with-AI-FF6B6B)](docs/AI_DISCLOSURE.md)

---

## ⚠️ Раскрытие сведений об ИИ-генерации

Проект в значительной степени разработан с помощью больших языковых моделей. Требования, ревью, проверка и выпуск — за человеком. Подробности в [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md); проект следует [AI Development Guidelines](https://github.com/styisme/ai-development-guidelines).

---

## ✨ Основные возможности

- **Два поколения протокола**: LocalSend `v2` (`prepare-upload`/`upload`/`cancel`) и `v2.1` (`send-request`/`send`); префикс `v1` тоже работает. Автоматический откат при 404/405.
- **Тройное обнаружение**: multicast `224.0.0.167:53317`, широковещание подсети и **глубокое HTTP-сканирование** (все интерфейсы, оба порта параллельно).
- **Докачка без перезаписи**: продолжение с дискового смещения; имена проходят `safe_filename` + `unique_path`, конфликты получают `(1)`.
- **Контроль доступа**: PIN (`401` + `X-LocalSend-Pin`), белые/чёрные списки отпечатков, фильтр опасных расширений (пропуск по файлам).
- **Защита от Zip Slip**: отклоняются абсолютные пути, буквы дисков, обход `..` и символические ссылки.
- **TLS**: `lspy cert` создаёт самоподписанную пару; обе стороны могут работать через HTTPS.
- **Между сетями**: через ntfy.sh, блоки по 2400 байт, 3 попытки, завершающий SHA-256.
- **Веб-страница состояния**, **10 языков интерфейса**.

---

## 📱 Быстрый старт

```bash
git clone https://github.com/styisme/lspy.git
cd lspy
python lspy.py --help          # без установки
pip install .                  # установить команду `lspy`

lspy serve --web
lspy scan
lspy send a.jpg --ip 192.168.1.20:53317 --pin 1234
lspy cross-send photo.zip
```

Python 3.8+, без зависимостей. Откройте TCP/UDP `53317`.

---

## 🛠️ Сборка и тесты

```bash
pip install .
python -m unittest discover -s tests -v
python scripts/sync_version.py --check
```

---

## 🚧 Риски и ограничения

1. **Высокая доля ИИ**: протокол, проверки безопасности и скрипты CI созданы при участии ИИ; обязательны человеческое ревью и проверка на реальных устройствах. Это не аудированная реализация.
2. **Межсетевой канал — открытый текст**: тема ntfy и есть PIN; утёк PIN — утёк файл. Не передавайте конфиденциальные данные.
3. **Однофайловая архитектура**: `lspy.py` около 1500 строк; удобно распространять, но слабая модульность и статический анализ.
4. **Самоподписанный TLS**: цепочки сертификатов не проверяются, защиты от MITM нет.

---

## 📜 Лицензия

MIT ([LICENSE](LICENSE)). Уведомление о совместимости: [LICENSE-LocalSend](LICENSE-LocalSend).
