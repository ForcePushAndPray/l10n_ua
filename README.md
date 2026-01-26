# Українська локалізація Odoo 19 CE

Комплексне рішення для управління бізнесом в Україні: HR, бухгалтерія, податки, банки, ПРРО, доставка, маркетплейси.

## Огляд модулів

| Категорія | Модулів | Статус |
|-----------|---------|--------|
| Базові | 1 | ✅ |
| Бухгалтерія | 3 | ✅ |
| Податки | 5 | ✅ |
| Банки | 4 | ✅ |
| ПРРО | 2 | ✅ |
| Доставка | 4 | ✅ |
| Маркетплейси | 3 | ✅ |
| HR | 10 | ✅ |
| **Всього** | **32** | |

---

## Архітектура модулів

![Module Architecture](diagrams/full_architecture.svg)

---

## Базовий модуль

### l10n_ua_account_base — Фундамент локалізації

**Призначення:** Базовий модуль для всіх українських локалізацій — довідники, валідації, утиліти та базовий облік.

| Модель | Опис | Записів |
|--------|------|---------|
| `l10n_ua.kved` | Класифікатор КВЕД-2010 | ~1000 |
| `l10n_ua.koatuu` | Довідник КАТОТТГ | 19000+ |
| `l10n_ua.tax.office` | Податкові інспекції (ДПІ) | ~40 |
| `l10n_ua.legal.form` | Організаційно-правові форми | 19 |
| `l10n_ua.journal.order` | Журнали-ордери (№1-7) | — |
| `l10n_ua.osv` | Оборотно-сальдова відомість | — |

**Розширення res.partner:**
- ЄДРПОУ (8 цифр з контрольною сумою)
- ІПН/РНОКПП (10 цифр з контрольною сумою)
- КВЕД (основний та додаткові)

**Розширення account.account:**
- План рахунків України (класи 0-9)
- Українська класифікація рахунків

**Утиліти (tools/):**
- `validators.py` — валідація ЄДРПОУ, ІПН, IBAN
- `formatters.py` — форматування дат, сум українською

---

## Бухгалтерія та податки

### l10n_ua_accounting — Функціонал бухгалтера (PLANNED)

**Поточний стан:** Кумулятивний модуль (bundle), встановлює залежності.

**План розвитку:**
- Кореневе меню "Бухгалтерія UA" (sequence=51)
- ПКО (Прибутковий касовий ордер, КО-1)
- ВКО (Видатковий касовий ордер, КО-2)
- Касова книга
- Акти наданих послуг
- Акти звірки взаєморозрахунків
- Баланс (Форма №1), Звіт про фінрезультати (Форма №2)

> **Примітка:** План рахунків, ОСВ та журнали-ордери реалізовані в `l10n_ua_account_base`.

### l10n_ua_assets — Основні засоби

- Групи ОЗ за ПКУ (1-16)
- Методи амортизації: прямолінійний, зменшення залишку, виробничий, кумулятивний
- Інвентарна картка ОЗ-6
- МНМА: списання 50/50 або 100%

### l10n_ua_tax — Податковий облік

| Податок | Ставка | Призначення |
|---------|--------|-------------|
| ПДФО | 18% | Податок на доходи фізосіб |
| ВЗ | 5% | Військовий збір |
| ЄСВ | 22% | Єдиний соціальний внесок |
| ПДВ | 20%/7%/0% | Податок на додану вартість |
| ЄП | 2-5% | Єдиний податок (групи 1-4) |

**Розширення res.company:**
- Організаційно-правова форма (ФОП, ТОВ, ПП, тощо)
- Податкова інспекція (ДПІ)
- Група єдиного податку (для ФОП)
- Ставка єдиного податку

### l10n_ua_account_vat — ПДВ

- Реєстр отриманих/виданих податкових накладних
- Податкова накладна (XML для ЄРПН)
- Розрахункова коригування (РК)
- Декларація з ПДВ

### l10n_ua_fop — Єдиний податок ФОП

- Книга обліку доходів (автозаповнення з банку)
- Декларація платника ЄП (групи 1, 2, 3)
- Розрахунок ЄСВ для ФОП

### l10n_ua_tax_cabinet — Кабінет платника

**Призначення:** Робота з електронним кабінетом платника податків (cabinet.tax.gov.ua).

| Тип документа | Код | Опис |
|---------------|-----|------|
| Декларація ЄП (ФОП) | F0103309 | Версія 9 |
| Декларація ЄП (ФОП) | F0103405 | Версія 5 |
| Звіт з ЄСВ | F0103308 | |
| Декларація з ПДВ | F0100210 | |
| Податкова накладна | J1201010 | |

**Функціонал:**
- Завантаження/створення документів
- Заповнення даних через wizard
- Генерація XML (windows-1251)
- Перегляд XML/PDF

### l10n_ua_tax_F0103309 — Декларація єдиного податку

Заповнення декларації F0103309 для ФОП 1-3 груп:
- Доходи по кварталах
- Автоматичний розрахунок податку
- Коди діяльності (КВЕД)

---

## Банківські інтеграції

![Bank Sync](diagrams/bank_sync.svg)

### l10n_ua_bank_sync — Базовий модуль

| Функція | Опис |
|---------|------|
| Довідник банків | МФО українських банків |
| Валідація IBAN | UA + 27 цифр |
| Імпорт виписок | Автоматичне розпізнавання контрагентів |
| Створення проводок | Автоматично з виписок |

### l10n_ua_bank_privat — ПриватБанк

- Privat24 Business API
- Автоімпорт виписок (scheduled/manual)
- Підтримка корпоративних карток

### l10n_ua_bank_mono — monobank

- monobank API
- Webhook для real-time оновлень
- Підтримка кількох рахунків

### l10n_ua_bank_currency_sync — Курси валют

- Синхронізація курсів з НБУ
- Автоматичне оновлення

---

## ПРРО (Програмні РРО)

![PRRO Workflow](diagrams/prro_workflow.svg)

### l10n_ua_prro_base — Базовий модуль

| Модель | Опис |
|--------|------|
| `l10n_ua.prro.config` | Налаштування ПРРО |
| `l10n_ua.prro.receipt` | Фіскальний чек |
| `l10n_ua.prro.receipt.line` | Рядок чека |
| `l10n_ua.prro.shift` | Зміна (X/Z-звіти) |

**Типи чеків:**
- Продаж / Повернення
- Службове внесення / видача готівки

**Методи оплати POS:**
- Готівка, Картка
- mono, LiqPay, NovaPay, RozetkaPay, WayForPay, EasyPay
- Подарунковий сертифікат

### l10n_ua_prro_checkbox — Checkbox

| Функція | Статус |
|---------|--------|
| Інтеграція з API | ✅ |
| Авторизація (login/password) | ✅ |
| Авторизація (PIN-код) | ✅ |
| Реєстрація чеків | ✅ |
| X-звіт / Z-звіт | ✅ |
| Службове внесення/видача | ✅ |
| Повернення товару | ✅ |
| Офлайн режим | ✅ |
| Чеки: text/html/png/qrcode | ✅ |

---

## Доставка

### l10n_ua_delivery_base — Базовий модуль

- Абстрактний mixin для перевізників
- Спільна модель відділень/поштоматів

### l10n_ua_delivery_novaposhta — Нова Пошта

| Функція | Статус |
|---------|--------|
| Створення ТТН | ✅ |
| Друк маркування | ✅ |
| Відстеження статусу | ✅ |
| Розрахунок вартості | ✅ |
| Довідник відділень | ✅ |
| Післяплата | ✅ |
| Зворотна доставка | ✅ |

### l10n_ua_delivery_meest — Meest

- Створення накладних
- Друк маркування
- Відстеження
- Довідник відділень

### l10n_ua_delivery_ukrposhta — Укрпошта

- Створення накладних
- Друк маркування
- Відстеження
- Довідник відділень

---

## Маркетплейси

### l10n_ua_marketplace_base — Базовий модуль

| Функція | Опис |
|---------|------|
| Синхронізація товарів | sync_products() |
| Синхронізація залишків | sync_stock() |
| Синхронізація цін | sync_prices() |
| Імпорт замовлень | import_orders() |
| Генерація YML фіду | generate_yml_feed() |

### l10n_ua_marketplace_rozetka — Rozetka

- YML фід для Rozetka
- Маппінг категорій
- Імпорт замовлень
- Оновлення статусів

### l10n_ua_marketplace_prom — Prom.ua

- Фід для Prom.ua
- Синхронізація через API
- Імпорт замовлень

---

## HR модулі

![HR Architecture](diagrams/module_architecture.svg)

### l10n_ua_hr — Базовий HR модуль

### l10n_ua_hr_base — Розширення працівників

| Модель | Опис |
|--------|------|
| `hr.employee` | РНОКПП, паспорт, військовий облік, пільги |
| `hr.kp2010` | Класифікатор професій ДК 003:2010 |
| `hr.staffing.table` | Штатний розпис |

### l10n_ua_hr_contract — Трудові договори

| Тип договору | Опис |
|--------------|------|
| permanent | Безстроковий |
| fixed_term | Строковий |
| civil | Цивільно-правовий |
| gig_contract | Гіг-контракт (Дія.City) |

**Також:**
- Графіки роботи (5-денка, змінний, гнучкий)
- Надбавки (за стаж, шкідливість, інтенсивність)

### l10n_ua_hr_documents — Накази

| Тип наказу | Форма |
|------------|-------|
| Прийом | П-1 |
| Переведення | П-5 |
| Звільнення | П-3 |
| Відпустка | П-4 |
| Премія | |
| Відрядження | |

### l10n_ua_hr_documents_certificates — Довідки

- Довідка про роботу
- Довідка про зарплату
- Довідка для банку

### l10n_ua_hr_holidays — Відпустки та лікарняні

| Тип | Опис |
|-----|------|
| Щорічна основна | 24 календарних дні |
| Додаткова | За шкідливі умови |
| Навчальна | Для здобуття освіти |
| Без збереження | За власний рахунок |
| Лікарняний | е-ТВН інтеграція |

### l10n_ua_hr_salary — Розрахунок зарплати

![Salary Calculation](diagrams/salary_calculation.svg)

| Показник | Формула |
|----------|---------|
| ПДФО | (Gross - ПСП) × 18% |
| Військовий збір | Gross × 5% |
| ЄСВ | min(max(Gross, МЗП), 15×МЗП) × 22% |
| ПСП | 50%/75%/100% прожиткового мінімуму |

### l10n_ua_hr_attendance_sheet — Табель обліку

- Табель П-5
- Автоматичне заповнення

### l10n_ua_hr_reports — Звітність ПФУ/ДПС

- Додаток 4ДФ
- Звіт ЄСВ
- XML експорт

---

## Встановлення

### Мінімальний набір (ФОП):
```bash
odoo-bin -d <database> -i l10n_ua_account_base,l10n_ua_tax,l10n_ua_fop,l10n_ua_bank_sync --stop-after-init
```

### Повний набір бухгалтерії:
```bash
odoo-bin -d <database> -i l10n_ua_accounting,l10n_ua_tax,l10n_ua_account_vat,l10n_ua_assets,l10n_ua_tax_cabinet --stop-after-init
```

### HR модулі:
```bash
odoo-bin -d <database> -i l10n_ua_hr_base,l10n_ua_hr_contract,l10n_ua_hr_documents,l10n_ua_hr_salary --stop-after-init
```

### ПРРО + Банки:
```bash
odoo-bin -d <database> -i l10n_ua_prro_checkbox,l10n_ua_bank_privat,l10n_ua_bank_mono --stop-after-init
```

### E-commerce:
```bash
odoo-bin -d <database> -i l10n_ua_delivery_novaposhta,l10n_ua_marketplace_rozetka --stop-after-init
```

### Оновлення:
```bash
odoo-bin -d <database> -u l10n_ua_account_base --stop-after-init
```

---

## Налаштування компанії

1. **Налаштування → Компанії → [Ваша компанія]**
2. Вкладка **"Ukrainian Tax Settings"**:
   - Організаційно-правова форма (ФОП, ТОВ, тощо)
   - Податкова інспекція
   - Група ФОП та ставка (якщо ФОП)
   - Коди діяльності (КВЕД)

---

## Структура меню

### Кореневі меню

| Меню | Sequence | Модуль | Опис |
|------|----------|--------|------|
| Invoicing | 50 | Odoo (account) | Стандартне меню → розширюємо |
| **Payroll** | 30 | l10n_ua_hr_salary | Зарплата |
| **Timesheet** | 50 | l10n_ua_hr_attendance_sheet | Табель обліку |
| **Bank UA** | 53 | l10n_ua_bank_sync | Банківські виписки |
| **Taxes UA** | 54 | l10n_ua_tax | Податковий облік |
| Employees | 60 | Odoo (hr) | Стандартне меню → розширюємо |

### Invoicing → Configuration → Ukraine

```
Ukraine
├── Directories
│   ├── KOATUU/KATOTTG          (l10n_ua_account_base)
│   └── KVED-2010               (l10n_ua_account_base)
├── UA Accounting
│   ├── Journal Orders          (l10n_ua_account_base)
│   └── Trial Balance (OSV)     (l10n_ua_account_base)
├── Fixed Assets
│   └── MNMA                    (l10n_ua_assets)
├── PRRO
│   ├── Configurations          (l10n_ua_prro_base)
│   ├── Shifts                  (l10n_ua_prro_base)
│   ├── Receipts                (l10n_ua_prro_base)
│   └── Checkbox                (l10n_ua_prro_checkbox)
├── Delivery
│   └── Warehouses              (l10n_ua_delivery_base)
└── Marketplaces
    ├── Configurations          (l10n_ua_marketplace_base)
    ├── Orders                  (l10n_ua_marketplace_base)
    └── Category Mapping        (l10n_ua_marketplace_base)
```

### Bank UA

```
Bank UA
├── Dashboard
├── Statements
│   ├── Statements
│   ├── Transactions
│   └── Generate Statement
├── Sync Jobs
│   └── Jobs
└── Configuration
    ├── Connections             (l10n_ua_bank_sync)
    ├── Currencies              (l10n_ua_bank_currency_sync)
    ├── Currency Rates          (l10n_ua_bank_currency_sync)
    └── Rate Providers          (l10n_ua_bank_currency_sync)
```

### Taxes UA

```
Taxes UA
├── Tax Documents               (l10n_ua_tax)
├── Tax Periods                 (l10n_ua_tax)
├── Tax Cabinet
│   └── Sync Documents          (l10n_ua_tax_cabinet)
├── VAT
│   ├── Tax Invoices            (l10n_ua_account_vat)
│   ├── VAT Registers           (l10n_ua_account_vat)
│   └── VAT Declarations        (l10n_ua_account_vat)
├── FOP (Single Tax)
│   ├── Income Books            (l10n_ua_fop)
│   └── Declarations            (l10n_ua_fop)
└── Configuration
    ├── Document Types          (l10n_ua_tax)
    ├── Budget Codes            (l10n_ua_tax)
    ├── Tax Offices (ДПІ)       (l10n_ua_account_base)
    └── Cabinet Connections     (l10n_ua_tax_cabinet)
```

### Employees (HR)

```
Employees
├── Documents
│   ├── Штатний розпис          (l10n_ua_hr_base)
│   ├── Salary Changes          (l10n_ua_hr_contract)
│   ├── Job Combining           (l10n_ua_hr_contract)
│   ├── Amendments              (l10n_ua_hr_contract)
│   ├── Кадрові накази          (l10n_ua_hr_documents)
│   ├── Order Templates         (l10n_ua_hr_documents)
│   ├── Personal Files          (l10n_ua_hr_documents)
│   └── Certificates            (l10n_ua_hr_documents_certificates)
├── Configuration → Ukraine
│   ├── Classifiers
│   │   ├── Professions (KP 2010)
│   │   ├── Education Levels
│   │   ├── Tariff Grades
│   │   └── Employee Benefits
│   └── Military Accounting
│       ├── Military Ranks
│       └── Territorial Centers
└── Reports
    ├── 1DF Reports             (l10n_ua_hr_reports)
    ├── D5 ESV Reports          (l10n_ua_hr_reports)
    └── Generate Report         (l10n_ua_hr_reports)
```

### Payroll

```
Payroll
├── Payslips                    (l10n_ua_hr_salary)
├── Batches                     (l10n_ua_hr_salary)
├── Execution Documents         (l10n_ua_hr_salary)
└── Configuration
    ├── PSP Parameters
    ├── Accrual Types
    └── Deduction Types
```

### Time Off (Відпустки)

```
Time Off
├── Sick Leaves                 (l10n_ua_hr_holidays)
├── Vacation Balances           (l10n_ua_hr_holidays)
├── Vacation Schedules          (l10n_ua_hr_holidays)
└── Vacation Calendar           (l10n_ua_hr_holidays)
```

### Timesheet (Табель)

```
Timesheet
├── Timesheets                  (l10n_ua_hr_attendance_sheet)
└── Configuration
    ├── Production Calendars
    └── Timesheet Codes
```

---

## Діаграми

Всі діаграми знаходяться в папці `diagrams/`:

| Файл | Опис |
|------|------|
| `full_architecture.puml` | Загальна архітектура всіх модулів |
| `menu_structure.puml` | Структура меню |
| `module_architecture.puml` | Архітектура HR модулів |
| `data_model.puml` | Модель даних HR |
| `prro_workflow.puml` | Процес фіскалізації чека |
| `bank_sync.puml` | Синхронізація банківських виписок |
| `hiring_process.puml` | Процес прийому на роботу |
| `salary_calculation.puml` | Розрахунок зарплати |
| `certificate_workflow.puml` | Життєвий цикл довідки |
| `order_workflow.puml` | Життєвий цикл наказу |

---

## Контакти

**Автори:** Святослав Надозірний, Ярослав Кравець
**Website:** https://ndev.online

---

## Ліцензія

LGPL-3.0
