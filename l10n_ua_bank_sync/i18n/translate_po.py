#!/usr/bin/env python3
"""Translate PO file for l10n_ua_hr_base module."""

import re

TRANSLATIONS = {
    # Common
    "Active": "Активний",
    "<span class=\"o_stat_text\">Sync Job</span>": "<span class=\"o_stat_text\">Завдання синхронізації</span>",
    "<span class=\"o_stat_text\">View Logs</span>": "<span class=\"o_stat_text\">Переглянути логи</span>",
    "Account": "Рахунок",
    "Additional data in JSON format": "Додаткові дані у форматі JSON",
    "Amount": "Сума",
    "Auto Sync": "Автосинхронізація",
    "Bank Configuration": "Налаштування банку",
    "Bank Connections": "Підключення до банків",
    "Bank Journal": "Банківський журнал",
    "Bank Statement": "Банківська виписка",
    "Bank Statements": "Банківські виписки",
    "Bank Sync Configuration": "Налаштування синхронізації банку",
    "Bank Sync Configurations": "Налаштування синхронізації банків",
    "Bank Sync Job": "Завдання синхронізації банку",
    "Bank Sync Log Entry": "Запис логу синхронізації банку",
    "Bank Sync Wizard": "Майстер синхронізації банку",
    "Bank UA": "Банк UA",
    "Can only fetch in draft or error state": "Можна отримати лише в стані чернетки або помилки",
    "Can only process in fetched or error state": "Можна обробити лише в стані отримано або помилки",
    "Closing Balance": "Залишок на кінець",
    "Configuration": "Налаштування",
    "Created Statements": "Створені виписки",
    "Custom Period": "Довільний період",
    "Custom Period...": "Довільний період...",
    "Data": "Дані",
    "Data (JSON)": "Дані (JSON)",
    "Date From must be before Date To": "Дата початку повинна бути раніше дати закінчення",
    "Date Range": "Діапазон дат",
    "Debug": "Налагодження",
    "Default Days Back": "Днів назад за замовчуванням",
    "Default number of days to fetch statements for": "Кількість днів за замовчуванням для отримання виписок",
    "Done": "Виконано",
    "Enable automatic synchronization via scheduled action": "Увімкнути автоматичну синхронізацію через заплановану дію",
    "Error": "Помилка",
    "Error Message": "Повідомлення про помилку",
    "Errors": "Помилки",
    "External ID": "Зовнішній ID",
    "Fetch from Bank": "Отримати з банку",
    "Fetched": "Отримано",
    "Fetching from Bank": "Отримання з банку",
    "Import": "Імпорт",
    "Import Jobs": "Завдання імпорту",
    "Imported": "Імпортовано",
    "Info": "Інформація",
    "Invalid Ukrainian IBAN: %s": "Невірний український IBAN: %s",
    "Job Count": "Кількість завдань",
    "Jobs": "Завдання",
    "Journal Entry": "Запис журналу",
    "Last 30 Days": "Останні 30 днів",
    "Last 7 Days": "Останні 7 днів",
    "Last Month": "Минулий місяць",
    "Last Sync": "Остання синхронізація",
    "Last Sync Job": "Останнє завдання синхронізації",
    "Level": "Рівень",
    "Line Count": "Кількість рядків",
    "Lines": "Рядки",
    "Log Entry": "Запис логу",
    "Logs": "Логи",
    "MFO Code": "Код МФО",
    "MFO code must be exactly 6 digits": "Код МФО повинен містити рівно 6 цифр",
    "Manual": "Вручну",
    "Message": "Повідомлення",
    "No payload to process. Fetch data first.": "Немає даних для обробки. Спочатку отримайте дані.",
    "No payload to reprocess": "Немає даних для повторної обробки",
    "Opening Balance": "Залишок на початок",
    "Partner": "Партнер",
    "Partner EDRPOU": "ЄДРПОУ партнера",
    "Partner IBAN": "IBAN партнера",
    "Partner Name": "Назва партнера",
    "Payload Fetched At": "Дані отримано о",
    "Payment Reference": "Призначення платежу",
    "Period": "Період",
    "Positive for incoming, negative for outgoing": "Додатне для вхідних, від'ємне для вихідних",
    "Processing": "Обробка",
    "Provider": "Провайдер",
    "Provider '%s' does not implement _fetch_from_bank method": "Провайдер '%s' не реалізує метод _fetch_from_bank",
    "Provider '%s' does not implement _parse_transactions method": "Провайдер '%s' не реалізує метод _parse_transactions",
    "Quick Select": "Швидкий вибір",
    "Raw Payload": "Сирі дані",
    "Raw Payload (JSON)": "Сирі дані (JSON)",
    "Raw response from bank API stored as JSON": "Сира відповідь від API банку, збережена як JSON",
    "Reconcile": "Звірити",
    "Reconciled": "Звірено",
    "Reprocess": "Повторна обробка",
    "Results": "Результати",
    "Source": "Джерело",
    "Start Sync": "Почати синхронізацію",
    "Statement": "Виписка",
    "Statement Count": "Кількість виписок",
    "Statements": "Виписки",
    "Status based on activities\\nOverdue: Due date is already passed\\nToday: Activity date is today\\nPlanned: Future activities.": "Статус на основі активностей\\nПрострочено: Термін вже минув\\nСьогодні: Дата активності сьогодні\\nЗаплановано: Майбутні активності.",
    "Sync Bank Statements": "Синхронізувати банківські виписки",
    "Sync Interval (hours)": "Інтервал синхронізації (години)",
    "Sync Job": "Завдання синхронізації",
    "Sync Jobs": "Завдання синхронізації",
    "Sync Logs": "Логи синхронізації",
    "Sync Now": "Синхронізувати зараз",
    "Sync Settings": "Налаштування синхронізації",
    "The currency used to enter statement": "Валюта для введення виписки",
    "This Month": "Цей місяць",
    "Timestamp": "Мітка часу",
    "Today": "Сьогодні",
    "Total": "Всього",
    "Total Credit": "Всього кредит",
    "Total Debit": "Всього дебет",
    "Transactions Found": "Знайдено транзакцій",
    "Ukrainian Bank Statement": "Українська банківська виписка",
    "Ukrainian Bank Statement Line": "Рядок української банківської виписки",
    "Ukrainian bank MFO code (6 digits)": "Код МФО українського банку (6 цифр)",
    "Unique transaction ID from bank": "Унікальний ID транзакції з банку",
    "Updated": "Оновлено",
    "Warning": "Попередження",
    "Yesterday": "Вчора",
    "config_id": "config_id",
    "e.g. PrivatBank Main Account": "напр. ПриватБанк Основний рахунок",
    "job_id": "job_id",
    "sync_job_id": "sync_job_id",
}


def is_english(text):
    """Check if text is primarily English (ASCII letters)."""
    if not text:
        return False
    ascii_letters = sum(1 for c in text if c.isascii() and c.isalpha())
    total_letters = sum(1 for c in text if c.isalpha())
    if total_letters == 0:
        return False
    return ascii_letters / total_letters > 0.8


def translate_po(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    result = []
    i = 0
    translated_count = 0
    untranslated = []

    while i < len(lines):
        line = lines[i]
        result.append(line)

        # Handle msgid (both single-line and multi-line)
        if line.startswith('msgid "'):
            if line == 'msgid ""':
                # Multi-line msgid starting with empty string
                msgid = ""
                j = i + 1
                while j < len(lines) and lines[j].startswith('"'):
                    msgid += lines[j][1:-1]
                    result.append(lines[j])
                    j += 1
            else:
                # Single-line or continuation msgid
                msgid = line[7:-1]
                j = i + 1
                while j < len(lines) and lines[j].startswith('"'):
                    msgid += lines[j][1:-1]
                    result.append(lines[j])
                    j += 1

            # Check if msgstr is empty and we have a translation
            if j < len(lines) and lines[j].startswith('msgstr "'):
                msgstr_line = lines[j]
                # Check if msgstr is empty (either 'msgstr ""' alone or followed by empty continuations)
                if msgstr_line == 'msgstr ""':
                    # Check if next lines are empty string continuations
                    k = j + 1
                    msgstr_empty = True
                    while k < len(lines) and lines[k].startswith('"'):
                        if lines[k] != '""':
                            msgstr_empty = False
                            break
                        k += 1

                    if msgstr_empty and msgid and msgid in TRANSLATIONS:
                        translation = TRANSLATIONS[msgid]
                        # Handle multi-line translations
                        if '\n' in translation:
                            result.append('msgstr ""')
                            for part in translation.split('\n'):
                                result.append(f'"{part}\\n"')
                            # Remove trailing \n from last part
                            if result[-1].endswith('\\n"'):
                                result[-1] = result[-1][:-3] + '"'
                        else:
                            result.append(f'msgstr "{translation}"')
                        translated_count += 1
                        i = j + 1
                        continue
                    elif msgstr_empty and msgid and is_english(msgid) and msgid not in TRANSLATIONS:
                        untranslated.append(msgid)

        i += 1

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(result))

    print(f"Translated {translated_count} strings")

    if untranslated:
        print(f"\nUntranslated English strings ({len(untranslated)}):")
        for s in sorted(set(untranslated)):
            print(f'    "{repr(s)[1:-1]}": "",')


if __name__ == '__main__':
    translate_po('uk_UA.po', 'uk_UA.po')
