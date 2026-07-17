# Бібліотека підпису IIT euscp («Підпис для WEB», WASM)

Сюди потрібно покласти файли бібліотеки клієнтського КЕП-підпису від
АТ «ІІТ» (euscp, режим WASM / чистий JS) — вони пропрієтарні й не входять
до цього репозиторію.

Типовий склад пакета IIT «Бібліотека підпису для WEB»:

- `euscp.js` (або `euscpm.js`) — головний JS-модуль;
- `euscp.worker.js`, `euscp.worker.wasm` — WebAssembly-воркер;
- `Modules/` — допоміжні модулі, якщо є у вашій версії.

Покладіть їх у цей каталог. Manifest підхоплює `euscp/**/*.js` глобом
(`__manifest__.py` → `web.assets_backend`), тож після додавання файлів і
`-u l10n_ua_tax_cabinet` бібліотека завантажиться перед віджетом
`erpn_sign_action.js`.

Віджет очікує глобальний об'єкт бібліотеки (`window.EndUserLibrary` /
`window.euscp` / `window.EndUser`) з promise-API. Точні виклики підпису
зосереджені в `_signInBrowser()` у `static/src/js/erpn_sign_action.js` —
за потреби підлаштуйте їх під версію API вашого пакета IIT.

## Де взяти файли (перевірено 2026-07)

Нам потрібен саме **JavaScript/WASM** варіант (без браузерного розширення):

1. **Офіційна сторінка завантажень IIT** — https://www.iit.com.ua/downloads
   - «Бібліотека підпису (java-скрипт, опис та настанови програмістам)» →
     `EUSignJavaScriptD.doc` (документація API + де брати самі файли):
     https://iit.com.ua/download/productfiles/EUSignJavaScriptD.doc
2. **Офіційний живий демо-майданчик** (віддає готові euscp*.js + WASM, доступний
   з України): http://js.sign.eu.iit.com.ua/  (та вибір режимів:
   http://sign.eu.iit.com.ua/). Файли можна взяти зі сторінки демо.
3. **Готова npm-дистрибуція** (бандлить `euscp.worker.js` + WASM):
   `@it-enterprise/digital-signature` — `npm i @it-enterprise/digital-signature`.
4. **Публічний приклад-дзеркало** (euscp.js/euscpm.js/euscpt.js/euutils.js/
   manager.js, без worker/wasm): github.com/gorserg/sign_sample →
   `public/js/lib/eu/`.

Мінімальний набір для pure-WASM режиму: `euscp.js`, `euscpm.js`,
`euscp.worker.js` + WASM-модулі (`*.wasm` / каталог `Modules/`). Файли
`euscpt.js` (транспорт для розширення) для WASM-режиму не потрібні.

**Ліцензія/застереження:** бібліотека IIT пропрієтарна. Використання для
підпису КЕП безкоштовне, але перед комітом файлів у публічний репозиторій
звірте умови розповсюдження IIT — можливо, тримати їх лише локально/приватно.

## Референс-проєкти на GitHub (як інтегрувати euscp у браузері)

- **kelatev/SA-SignInfo** (TypeScript) — найповніша обгортка EndUser:
  worker `euscp.worker.js?maxDataSize=25`, режими SW(WASM)/JS(agent), точні
  сигнатури `ReadPrivateKeyBinary` / `SignData` / `SignDataInternal`
  (`src/EUSign/EndUserLibrary.ts`). Наш `_signInBrowser()` звірено саме з ним.
- **MeinLiX/CertVal** (TypeScript) — `CertVal.Web/src/lib/iit/signClient.ts`,
  клієнт підпису IIT.
- **NadiiaStoiko/modern-sign-server** — HTML-демо із `euscp.worker.js`.
- **gnelitsa/EUSignWidget-Usage-20200922** (JS) — приклад використання
  EUSign-віджета.
- **balrogden/EUSignES6** (JS) — ES6-обгортка EUSign.
- **gorserg/sign_sample** — статичне дзеркало файлів `public/js/lib/eu/`
  (euscp.js/euscpm.js/euscpt.js/euutils.js/manager.js).
- **@it-enterprise/digital-signature** (npm) — бандл із worker+WASM.
- Серверні/десктопні обгортки (для довідки): GorulkoAV/EUSignDFS (C#),
  matasarei/euspe (PHP), dstucrypt/social.eusign та muromec/flask-eusign-demo
  (Python, авторизація через eusign.org).

## Web-розширення (альтернатива, якщо оберете інший режим)
Інсталятори хост-агента: `EUSignWebInstall.exe/.msi/.pkg`, `euswi.deb/.rpm`
з тієї ж сторінки https://www.iit.com.ua/downloads + браузерне розширення
«ІІТ Користувач ЦСК-1. Бібліотека підпису (web-розширення)» з Chrome Web Store.
Цей режим змінює виклики у `_signInBrowser()` (інтерфейс `EUSignCPWebSign`).
