[简体中文](README.md) | [繁體中文](README_zh_TW.md) | [English](README_EN.md) | [日本語](README_ja.md) | [**한국어**](README_ko.md) | [Deutsch](README_de.md) | [Français](README_fr.md) | [Español](README_es.md) | [Русский](README_ru.md) | [Português](README_pt.md)

# lspy

> LocalSend 프로토콜의 CLI 구현. 단일 파일, 서드파티 의존성 없음. 휴대폰은 LocalSend, PC는 명령 한 줄로 파일 송수신. ntfy.sh를 통한 크로스 네트워크 중계 지원.

[![CI](https://github.com/styisme/lspy/actions/workflows/ci.yml/badge.svg)](https://github.com/styisme/lspy/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.28.3-512BD4)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Made with AI](https://img.shields.io/badge/made%20with-AI-FF6B6B)](docs/AI_DISCLOSURE.md)

---

## ⚠️ AI 생성 공개

이 프로젝트는 개발 과정에서 대규모 언어 모델의 도움을 많이 받았습니다. 요구사항, 검토, 검증, 릴리스는 사람이 담당합니다. 자세한 내용은 [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md)를 참고하고, [AI 개발 가이드라인](https://github.com/styisme/ai-development-guidelines)을 따릅니다.

---

## ✨ 주요 기능

- **두 가지 프로토콜**: LocalSend `v2`(`prepare-upload`/`upload`/`cancel`)와 `v2.1`(`send-request`/`send`), `v1` 프리픽스도 지원. 404/405 시 자동 폴백.
- **세 가지 탐색**: 멀티캐스트 `224.0.0.167:53317`, 서브넷 브로드캐스트, **HTTP 심층 스캔**(모든 NIC·두 포트 병렬).
- **이어받기와 덮어쓰기 방지**: 세션 내 디스크 오프셋부터 계속. 저장 이름은 `safe_filename` + `unique_path`, 충돌 시 `(1)` 부여.
- **접근 제어**: PIN(`401` 요구/오류, 같은 IP 에서 3 회 연속 실패 시 `429` — LocalSend 와 동일), 지문 화이트/블랙리스트, 위험 확장자 필터(파일 단위 건너뛰기).
- **Zip Slip 방어**: 절대 경로, 드라이브 문자, `..` 탈출, 심볼릭 링크 거부.
- **TLS**: `lspy cert`로 자체 서명 인증서 생성, 양쪽 모두 HTTPS 사용 가능.
- **크로스 네트워크**: ntfy.sh 경유, 2400바이트 청크, 3회 재시도, SHA-256 + 길이 꼬리 검증.
- **Web 공유 페이지**(업로드 / 다운로드 / 텍스트, watchsend 이식; 페이지는 브라우저 `Accept-Language` 를 따름), **10개 UI 언어**.
- **파일별 sha256 검증**（공식 `createChecksums` / `verifyChecksums` 와 동일）: 보내는 쪽이 `files[].sha256` 에 각 파일 해시를 넣고, `verify_checksum` 이 켜진 받는 쪽이 공식과 같은 방식으로 검증합니다. 불일치하면 `422 Checksum mismatch` 를 반환하고 저장된 파일을 삭제합니다. 평문 HTTP 전송 시 암호화되지 않았음을 알려 줍니다.
- **네트워크 진단**（공식 `troubleshoot_page` 이식）: `lspy troubleshoot` 또는 메뉴 `9` 로 포트를 열 수 있는지 확인하고, 로컬 주소(IPv4 우선, `fe80` 링크 로컬 제외)를 나열하며, Windows 방화벽 `netsh advfirewall ... localport=` 규칙을 출력합니다. AP 격리로 멀티캐스트가 막혀도 HTTP 스캔은 동작한다는 점도 알려 줍니다.
- **무작위 별칭과 설정 가능한 기기 정보**（공식 `alias_generator`, `deviceType` / `deviceModel` 대응）: 첫 실행 시 "형용사+과일" 별칭을 생성해 저장하므로 호스트 이름이 LAN 에 노출되지 않습니다. `device_type` / `device_model` 이 `info` 에 알리는 유형과 모델을 정하며 설정 11·12 번에서도 바꿀 수 있습니다.
- **기록 및 디버그**(역시 watchsend 이식): `history --delete N` / `--clear` / `--unzip N`(ZIP 은 📦, Zip Slip 방지 포함), `--debug-keys` 로 i18n 원본 키 표시.
- **수신 편의**: 10 KB 이하 `.txt`는 수신 즉시 클립보드로 복사되며(`clipboard_text`로 끌 수 있음), 기록은 `history_max`(기본 300)로 오래된 항목부터 정리되고 `info`는 `[IPv6]:포트`도 함께 출력합니다.
- **tkinter 없이도 파일 선택**: 내장된 [cfdialog](https://github.com/styisme/cfdialog) 0.3.0(MIT, 단일 파일)이 tkinter 대화상자 대신 터미널 브라우저를 띄웁니다(번호 이동, `g` 파티션, `h` 숨김 파일, `a`/`c`/`d` 다중 선택). 저장 폴더 설정에서 `?`를 입력하면 폴더 탐색이 열립니다. `config --set force_cfdialog=true`로 터미널 브라우저를 강제할 수 있습니다(tkinter는 건너뜁니다). Android에서는 tkinter를 건너뛰고(Tk가 거의 없음) 바로 터미널 브라우저를 엽니다.

---
- **어느 화면에서나 수신**: 메뉴, 설정, 파일 선택 등 모든 입력 지점이 수신 대기열을 감시해 전송이 들어오면 즉시 수락 요청을 띄웁니다. `auto_accept`가 켜져 있으면 묻지 않고 바로 수신 상세로 들어가며, 완료 후 Enter로 원래 화면으로 돌아갑니다.
- **전송 후 대기**: 전송이 끝나도 바로 종료되지 않고 Enter를 눌러야 메뉴로 돌아갑니다.

## 📱 빠른 시작

```bash
git clone https://github.com/styisme/lspy.git
cd lspy
python lspy.py --help          # 설치 없이 실행
pip install .                  # lspy 명령으로 설치

lspy serve --web               # 수신 및 상태 페이지 열기
lspy scan
lspy send a.jpg --ip 192.168.1.20:53317 --pin 1234
lspy cross-send photo.zip
```

Python 3.8+, 외부 의존성 없음. TCP/UDP `53317` 포트를 열어 두세요.

---

## 🛠️ 빌드와 테스트

```bash
pip install .
python -m unittest discover -s tests -v
python scripts/sync_version.py --check
pip install pyinstaller && python scripts/build_binary.py
```

Python 없이 [Release](https://github.com/styisme/lspy/releases)의 단일 실행 파일을 사용할 수 있습니다: Windows `lspy-<버전>-windows-x64.exe`, Linux `lspy-<버전>-linux-x86_64`.

`CHANGELOG.md` 변경을 `main`에 푸시하면 Windows / Linux에서 실행 파일을 빌드하고 wheel, sdist와 함께 자동으로 태그와 Release를 생성합니다.


---

## 🚧 위험과 한계

1. **AI 참여도 높음**: 프로토콜, 보안 검증, CI 스크립트가 AI 지원으로 생성됨. 사람의 검토와 실기기 검증이 필요하며 감사된 구현이 아님.
2. **크로스 네트워크는 공중망 평문**: ntfy 토픽이 곧 PIN이며, PIN 노출은 파일 노출. 민감한 데이터를 보내지 마세요.
3. **단일 파일 구조**: `lspy.py` 약 1500줄. 배포는 쉽지만 모듈화와 정적 분석은 약함.
4. **자체 서명 TLS**: 인증서 체인을 검증하지 않아 MITM에 취약.

---

## 📜 라이선스

MIT ([LICENSE](LICENSE)). 프로토콜 호환성 안내는 [LICENSE-LocalSend](LICENSE-LocalSend).
