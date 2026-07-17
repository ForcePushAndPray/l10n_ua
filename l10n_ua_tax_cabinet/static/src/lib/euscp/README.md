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

Джерело: https://iit.com.ua/ (розділ «Бібліотека підпису»).
