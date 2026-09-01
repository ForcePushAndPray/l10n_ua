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

## ⚠️ Обов'язково: збірка з підтримкою ДСТУ 7564:2014 («Купина»)

**Дедлайн — 01.09.2026.** Україна завершує перехід КЕП з ГОСТ 34.311-95 на
національний стандарт геш-функції ДСТУ 7564:2014. З 10.02.2026 нові ключі
формуються за посиленим алгоритмом, з 01.09.2026 усі нові сертифікати —
виключно за новим. ІКС мають одночасно перевіряти і старі, і нові підписи
протягом усього строку дії сертифікатів
([ЦЗО](https://czo.gov.ua/edp-legislation-clarification?id=9)).

Криптографія живе **всередині** бібліотеки IIT, а не в нашому коді:
`kep_sign_service.js` викликає `SignData(data, asBase64)` /
`SignDataInternal(appendCert, data, asBase64)`, які **не приймають** параметра
алгоритму. Тобто підлаштовувати модуль не треба — треба покласти сюди
правильну збірку.

### Як перевірити збірку, що лежить у вас

Назви алгоритмів — відкритим текстом у `eusw.js` і `euscp.worker.js`:

```bash
grep -ao "EU_CTX_HASH_ALGO_[A-Z0-9_]*" eusw.js | sort -u
grep -ao "EU_CTX_SIGN_[A-Z0-9_]*"      eusw.js | sort -u
```

Збірка **придатна**, якщо серед констант є щось на кшталт
`EU_CTX_HASH_ALGO_DSTU7564` і відповідний `EU_CTX_SIGN_DSTU4145_WITH_DSTU7564`.

Збірка **непридатна**, якщо перелік обривається на `GOST34311`:

```
EU_CTX_HASH_ALGO_UNKNOWN, EU_CTX_HASH_ALGO_GOST34311,
EU_CTX_HASH_ALGO_SHA160, EU_CTX_HASH_ALGO_SHA224, ...
EU_CTX_SIGN_UNKNOWN, EU_CTX_SIGN_DSTU4145_WITH_GOST34311,
EU_CTX_SIGN_RSA_WITH_SHA, EU_CTX_SIGN_ECDSA_WITH_SHA
```

Мало того, що константи «Купини» немає — воркер сам жорстко призначає геш за
типом ключа:

```js
case EU_CERT_KEY_TYPE_DSTU4145:
    signAlgos.push(EU_CTX_SIGN_DSTU4145_WITH_GOST34311);
```

тобто для ключа ДСТУ 4145 старий геш береться беззастережно, і з нового
сертифіката підпис не вийде.

**Станом на 2026-08-29 збірка, що використовувалась у розробці** (файли від
17.07.2026, `euscpm.js` повідомляє `Version: 1.0.3`), — **непридатна** за цією
перевіркою. Її треба замінити свіжою з IIT до 01.09.2026, інакше зупиниться
реєстрація ПН в ЄРПН і подання декларацій (4ДФ/Д5, ФОП, запити до кабінету).

Відстежується в #194.

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
