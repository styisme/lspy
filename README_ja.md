[简体中文](README.md) | [繁體中文](README_zh_TW.md) | [English](README_EN.md) | [**日本語**](README_ja.md) | [한국어](README_ko.md) | [Deutsch](README_de.md) | [Français](README_fr.md) | [Español](README_es.md) | [Русский](README_ru.md) | [Português](README_pt.md)

# lspy

> LocalSend プロトコルの CLI 実装。単一ファイル・サードパーティ依存ゼロ。スマホは LocalSend、PC はコマンド 1 本でファイル送受信。ntfy.sh 経由のクロスネットワーク中継にも対応。

[![CI](https://github.com/styisme/lspy/actions/workflows/ci.yml/badge.svg)](https://github.com/styisme/lspy/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.20.1-512BD4)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Made with AI](https://img.shields.io/badge/made%20with-AI-FF6B6B)](docs/AI_DISCLOSURE.md)

---

## ⚠️ AI 生成に関する開示

本プロジェクトは開発の大部分で LLM による生成支援を受けています。要件定義・レビュー・検証・リリースは人間が担当します。詳細は [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md) を参照し、[AI 開発ガイドライン](https://github.com/styisme/ai-development-guidelines) に準拠しています。

---

## ✨ 主な機能

- **プロトコル両対応**: LocalSend `v2`（`prepare-upload`/`upload`/`cancel`）と `v2.1`（`send-request`/`send`）、`v1` プレフィックスも利用可。404/405 で自動フォールバック。
- **3 種類の探索**: マルチキャスト `224.0.0.167:53317`、サブネットブロードキャスト、**HTTP ディープスキャン**（全 NIC・両ポート並列）。
- **レジュームと上書き防止**: セッション内はディスク上のオフセットから継続。保存名は `safe_filename` + `unique_path` で衝突時に `(1)` を付与。
- **アクセス制御**: PIN（`401` + `X-LocalSend-Pin`）、フィンガープリントのホワイト/ブラックリスト、危険拡張子フィルタ（ファイル単位でスキップ）。
- **Zip Slip 対策**: 絶対パス・ドライブレター・`..` トラバーサル・シンボリックリンクを拒否。
- **TLS**: `lspy cert` で自己署名証明書を生成、送受信とも HTTPS 可。
- **クロスネットワーク**: ntfy.sh 経由。2400 バイト分割、3 回リトライ、SHA-256 + 長さの末尾検証。
- **Web ステータスページ** と **10 言語 UI**。

---

## 📱 クイックスタート

```bash
git clone https://github.com/styisme/lspy.git
cd lspy
python lspy.py --help          # インストール不要
pip install .                  # lspy コマンドとして導入

lspy serve --web               # 受信（ステータスページも起動）
lspy scan
lspy send a.jpg --ip 192.168.1.20:53317 --pin 1234
lspy cross-send photo.zip
```

Python 3.8+、依存パッケージなし。TCP/UDP `53317` を開放してください。

---

## 🛠️ ビルドとテスト

```bash
pip install .
python -m unittest discover -s tests -v
python scripts/sync_version.py --check
pip install pyinstaller && python scripts/build_binary.py
```

Python 不要でも [Release](https://github.com/styisme/lspy/releases) の単一ファイル版を使えます：Windows `lspy-<版>-windows-x64.exe`、Linux `lspy-<版>-linux-x86_64`。

`CHANGELOG.md` の変更を `main` にプッシュすると、Windows / Linux で実行ファイルをビルドし、wheel・sdist と合わせて自動でタグ付け・Release 公開します。


---

## 🚧 リスクと制限

1. **AI 関与度が高い**: プロトコル・安全性検証・CI スクリプトは AI 支援生成。人間のレビューと実機検証が前提で、監査済み実装ではありません。
2. **クロスネットワークは公衆網の平文**: ntfy のトピック名が PIN そのもの。機密データを送らないでください。
3. **単一ファイル構成**: `lspy.py` 約 1500 行。配布は容易ですが、モジュール化と静的解析は弱い。
4. **自己署名 TLS**: 証明書チェーンを検証しないため MITM 耐性はありません。

---

## 📜 ライセンス

MIT（[LICENSE](LICENSE)）。プロトコル互換性の注記は [LICENSE-LocalSend](LICENSE-LocalSend)。
