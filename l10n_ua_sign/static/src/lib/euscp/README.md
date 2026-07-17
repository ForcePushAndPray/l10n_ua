# Бібліотека підпису IIT euscp («Підпис для WEB», WASM)

Сюди потрібно покласти файли бібліотеки клієнтського КЕП-підпису від
АТ «ІІТ» (euscp, режим WASM / чистий JS) — вони пропрієтарні й не входять
до цього репозиторію (gitignored).

Мінімальний набір для pure-WASM режиму: `euscp.js`, `euscpm.js`, `euutils.js`,
`eusw.js`, `euscp.worker.js` (+ WASM-модулі, якщо окремо). Файл `euscpt.js`
(транспорт для розширення) для WASM-режиму не потрібен.

Файли підвантажуються **ліниво за URL** при підписі (не через
`web.assets_backend`): worker ~16МБ, euscp.js ~5МБ — у бандлі це зламало б
worker і роздуло кожну сторінку. Базовий URL і порядок скриптів — у
`static/src/js/kep_sign_service.js` (`EUSCP_BASE`, `EUSCP_SCRIPTS`). Достатньо
покласти файли сюди — оновлювати модуль не треба.

Сервіс очікує глобальний об'єкт бібліотеки (`window.EndUserLibrary` /
`window.euscp` / `window.EndUser`) з promise-API. Точні виклики підпису
зосереджені в `kep_sign_service.js` (`signDocuments` / `signOneDocument`) —
за потреби підлаштуйте під версію API вашого пакета IIT (EUSignJavaScriptD.doc).

## Де взяти файли (перевірено 2026-07)

Нам потрібен саме **JavaScript/WASM** варіант (без браузерного розширення):

1. **Офіційна сторінка завантажень IIT** — https://www.iit.com.ua/downloads
   - «Бібліотека підпису (java-скрипт, опис та настанови програмістам)» →
     `EUSignJavaScriptD.doc`:
     https://iit.com.ua/download/productfiles/EUSignJavaScriptD.doc
2. **Офіційний живий демо-майданчик** (віддає готові euscp*.js + WASM, доступний
   з України): http://js.sign.eu.iit.com.ua/  (вибір режимів:
   http://sign.eu.iit.com.ua/).
3. **Готова npm-дистрибуція** (бандлить `euscp.worker.js` + WASM):
   `@it-enterprise/digital-signature`.
4. **Публічне дзеркало-приклад**: github.com/kelatev/SA-SignInfo →
   `public/eusign/euscp.worker.js` + `src/EUSign/eusw.js` (реальні файли);
   github.com/gorserg/sign_sample → `public/js/lib/eu/`.

**Ліцензія/застереження:** бібліотека IIT пропрієтарна. Підпис КЕП безкоштовний,
але перед комітом файлів у публічний репозиторій звірте умови розповсюдження IIT —
тримайте їх лише локально/приватно.

## Референс-проєкти на GitHub (як інтегрувати euscp у браузері)

- **kelatev/SA-SignInfo** (TypeScript) — найповніша обгортка EndUser: worker
  `euscp.worker.js`, режими SW(WASM)/JS(agent), точні сигнатури
  `ReadPrivateKeyBinary` / `SignData` / `SignDataInternal`
  (`src/EUSign/EndUserLibrary.ts`). Наш сервіс звірено саме з ним.
- **MeinLiX/CertVal** (TS) — `signClient.ts`, клієнт підпису IIT.
- **NadiiaStoiko/modern-sign-server** — HTML-демо з `euscp.worker.js`.
- **gnelitsa/EUSignWidget-Usage-20200922**, **balrogden/EUSignES6** (JS).
- Серверні/десктопні (довідково): GorulkoAV/EUSignDFS (C#), matasarei/euspe (PHP),
  dstucrypt/social.eusign, muromec/flask-eusign-demo (Python).

## Web-розширення (альтернатива)
Інсталятори хост-агента `EUSignWebInstall.exe/.msi/.pkg`, `euswi.deb/.rpm` з
https://www.iit.com.ua/downloads + розширення з Chrome Web Store. Цей режим
змінює виклики у `kep_sign_service.js` (інтерфейс `EUSignCPWebSign`).
