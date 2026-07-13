# HOWTO: Ціни постачальників (імпорт прайс-листів)

← [Назад до документації](../../README.md) · [Опис домену](../supplier_prices.md)

> Покроковий сценарій імпорту прайс-листа постачальника у `product.supplierinfo`.
> Флоу можна відтворити на демо-сервері **[demo.ndev.online](https://demo.ndev.online)**
> (компанія _ТОВ «Тестова Компанія»_) — дані на демо **не видаляються**, його можна
> наповнювати під час тестування.
>
> Це **повністю реалізований рушій із тестами** (усі 6 модулів позначені ✅). Локальний
> файл + CSV-парсер проганяються **без жодних зовнішніх систем** — достатньо файлу з диска.
> Джерела **SFTP** та **HTTP API** потребують доступу до сервера постачальника (див.
> примітку в кроці 3.2). Деталі архітектури, state machine й моделей —
> у [supplier_prices_architecture.md](../supplier_prices_architecture.md).

Скріншоти — у теці [`img/supplier_prices/`](img/supplier_prices/).

---

## 0. Застосунок і меню

Рушій вбудовано в застосунок **Закупівлі**. Верхнє меню **Закупівлі → Supplier Prices**:

| Пункт меню | Призначення |
|-----------|-------------|
| **Imports** | Прогони імпорту (state machine draft → done) |
| **Configuration → Sources** | Джерела прайсів постачальників |
| **Configuration → Mappings** | Маппінг колонок файлу на поля Odoo |

Два незалежні шари налаштовуються на джерелі:

- **fetcher_type** — _звідки_ взяти файл: `manual` (ручне завантаження), `api`, `sftp`;
- **parser_type** — _як_ розібрати файл: `json`, `csv`, `xml`, `xlsx`.

Парсер і завантажувач комбінуються довільно (наприклад SFTP + XLSX, локальний файл + CSV).

> _Скриншот:_ `00-menu.png`

---

## 1. Створення джерела прайсу постачальника

**Закупівлі → Supplier Prices → Configuration → Sources → Новий.** Ключові поля джерела
(`l10n_ua.supplier.price.source`):

- **Постачальник** (`partner_id`) — контрагент, чиї ціни імпортуємо;
- **Компанія** (`company_id`) — необов'язкова; порожнє значення = ціни глобальні для всіх
  компаній групи;
- **Валюта за замовчуванням** — застосовується до рядків без власної валюти;
- **Дія на невідомий SKU** (`unknown_sku_action`): `skip` (пропустити), `log_only`
  (лише залогувати), `create_product` (створити товар), `error_stop` (зупинити з помилкою);
- **Авто-синхронізація** (`auto_sync_active`, `sync_interval_hours`) — крон сам створює
  нові імпорти за інтервалом;
- **Таймаути** (`fetch_timeout`, `parse_timeout`, `apply_timeout`,
  `watchdog_timeout_minutes`) — захист від зависання воркера.

> _Скриншот:_ `01-source-form.png`

---

## 2. Вибір формату-парсера (parser_type)

Поле **parser_type** визначає, як розбирати файл. Значення додаються встановленими
модулями-парсерами:

| parser_type | Модуль | Синтаксис `source_path` у маппінгу |
|-------------|--------|------------------------------------|
| `json` | `_base` (вбудований) | dotted + `[n]` + `[*]`: `items[*].price.value` |
| `csv` | `_csv` | назва колонки (з header) або індекс `2` (без header) |
| `xml` | `_xml` | відносний XPath: `./code/text()`, `@sku`, `string(./name)` |
| `xlsx` | `_xlsx` | назва колонки, літера `A`/`AC` або індекс |

Параметри конкретного парсера задаються JSON-полем **parser_config** на маппінгу
(крок 4), наприклад для CSV: `{"delimiter": ";", "encoding": "windows-1251", "has_header": true}`.

> _Скриншот:_ `02-parser-type.png`

---

## 3. Вибір завантажувача джерела (fetcher_type)

Поле **fetcher_type** визначає, звідки береться файл.

### 3.1. `manual` — локальний файл (без зовнішніх систем)

Базовий режим: файл завантажується вручну прямо в імпорт (крок 5). Нічого налаштовувати не
треба — ідеально для першого тесту й для разових прайсів.

### 3.2. `api` / `sftp` — зовнішнє джерело

Реквізити підключення задаються JSON-полем **connection_config** на джерелі:

- **HTTP API** (`l10n_ua_supplier_prices_api`, потрібен `requests`): `url`, `method`,
  `auth_type` (`none`/`basic`/`bearer`/`api_key_header`), облікові дані, `response_type`
  (`file` або `json_indirect` — відповідь із посиланням на файл);
- **SFTP** (`l10n_ua_supplier_prices_sftp`, потрібен `paramiko`): `host`, `port`,
  `username`, `password` або `key_file`, `remote_path`, `host_key_policy`.

> ⚠️ **Джерела SFTP та API потребують доступу до сервера постачальника** (мережа, облікові
> дані, ключі). Без реального ендпоінта їх не проженеш — для локального тесту беріть
> `manual` + CSV. Наразі облікові дані у `connection_config` зберігаються відкритим текстом;
> для production варто винести у зашифроване сховище. Схеми конфігів усіх завантажувачів —
> у [supplier_prices_architecture.md](../supplier_prices_architecture.md).

> _Скриншот:_ `03-fetcher-type.png`

---

## 4. Маппінг колонок

**Configuration → Mappings → Новий** (`l10n_ua.supplier.price.mapping`), потім прив'яжіть
маппінг до джерела. Маппінг описує, як витягти поля з файлу:

- **record_path** — шлях до записів: `items` (JSON), `//product` (XPath); для табличних
  форматів (CSV/XLSX) не потрібен;
- **parser_config** — JSON із параметрами обраного парсера;
- **Поля маппінгу** (`.mapping.field`) — по рядку на кожне цільове поле.

Кожен рядок поля має:

| Атрибут | Приклад | Призначення |
|---------|---------|-------------|
| **target** | `sku`, `name`, `price`, `currency`, `qty_min`, `uom`, `barcode` | Куди пишемо |
| **source_path** | `Ціна` / `2` / `./price/@value` | Звідки беремо (залежить від парсера) |
| **required** | `true` | Помилка, якщо відсутнє |
| **default_value** | `UAH` | Значення, якщо відсутнє і не required |
| **transform** | `to_float`, `parse_date`, `strip`, `multiply` | Перетворення значення |
| **transform_param** | `%d.%m.%Y` | Параметр трансформації |

Українська специфіка: `to_float` перетворює ціну з комою (`"15,50"` → `15.50`), `parse_date`
з форматом `%d.%m.%Y` розбирає `"17.04.2026"`. Мінімально потрібні target: **sku** і **price**.

> _Скриншот:_ `04-mapping.png`

---

## 5. Запуск імпорту (state draft → done)

**Supplier Prices → Imports → Новий** (або кнопка **Create Import** на джерелі). Оберіть
джерело; для `manual` — прикріпіть файл прайсу. Далі три кнопки в шапці ведуть імпорт
(`l10n_ua.supplier.price.import`) по state machine:

```
draft → fetching → fetched → parsing → parsed → applying → done
                                                          ↘ error
```

1. **Fetch** — `_do_fetch()` заповнює `raw_file` (для `manual` файл уже прикріплено;
   завантажувачі api/sftp тягнуть його із зовнішнього джерела) → **fetched**;
2. **Parse** — `_do_parse()` розбирає `raw_file` у рядки `import.line` за маппінгом →
   **parsed**. Raw-файл зберігається, тож парсинг можна повторити без повторного завантаження;
3. **Apply** — `_do_apply()` створює/оновлює `product.supplierinfo` для кожного рядка → **done**.

Action-методи **не викидають UserError** на помилці: імпорт переходить у **error**,
причина пишеться в `error_log` і чатер. Кнопка **Restart** повертає імпорт у `draft`.
Лічильники прогону: `line_count`, `matched_count`, `unknown_count`, `error_count`. Рядок
у статусі `unknown` обробляється згідно з `unknown_sku_action` джерела (крок 1).

> _Скриншоти:_ `05-import-form.png`, `06-import-lines.png`

---

## 6. Результат — оновлення `product.supplierinfo`

Після **Apply** для кожного розпізнаного рядка створюється або оновлюється запис
постачальника (`product.supplierinfo`): товар шукається за парою _постачальник +
`product_code` (SKU)_. У картці товару (вкладка **Закупівлі → Постачальники**) з'являються
ціна, мінімальна кількість, валюта й дата з прайсу. Саме ці ціни далі підставляються в
замовлення на закупівлю.

> _Скриншот:_ `07-supplierinfo.png`

---

## Контрольний чек-лист флоу

- [x] Джерело прайсу створюється (постачальник, parser_type, fetcher_type, дія на unknown SKU)
- [x] Парсери CSV/XML/XLSX + вбудований JSON; завантажувачі manual/API/SFTP комбінуються довільно
- [x] Маппінг колонок (target → source_path, required, default, transform) прив'язується до джерела
- [x] Локальний файл + CSV проганяється без зовнішніх систем
- [x] State machine draft → fetching → fetched → parsing → parsed → applying → done (+ error/restart)
- [x] Apply створює/оновлює `product.supplierinfo` (пошук за партнером + SKU)
- [x] Усі 6 модулів мають робочі юніт-тести (base 44, csv 10, xlsx 13, xml 9, api 12, sftp 10)
- [ ] Скріншоти додати у `img/supplier_prices/` (див. імена біля кроків)
