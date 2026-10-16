"""Формат обміну M.E.Doc: контейнер ``ZVIT`` версії 4.1.

Опис структури — https://medoc.ua/page/integrationxml. Файл кодується у
windows-1251; один файл несе довільну кількість документів (``CARD``) однієї
організації. Модуль не залежить від Odoo, тож тестується без бази.
"""
from xml.sax.saxutils import escape, quoteattr

ZVIT_VERSION = '4.1'
ENCODING = 'windows-1251'


def fmt_date(value):
    """Дата у форматі дд.мм.рррр."""
    return value.strftime('%d.%m.%Y') if value else ''


def fmt_number(value, digits=2):
    """Число з крапкою без зайвих нулів: 1200.00 → '1200', 15.950 → '15.95'."""
    text = f'{value or 0.0:.{digits}f}'
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return '0' if text in ('', '-0') else text


class MedocCard:
    """Один документ у файлі: службові поля картки та рядки ``ROW``."""

    def __init__(self, fields, primary=False):
        # fields — впорядкований перелік (тег, значення) для CARD/FIELDS
        self.fields = list(fields)
        self.primary = primary
        self.rows = []

    def add(self, name, value, tab=0, line=0):
        """Додати реквізит. Порожні значення пропускаються цілим блоком ROW:
        M.E.Doc не допускає ``<VALUE></VALUE>`` та ``<VALUE/>``."""
        if value is None or value is False:
            return
        text = str(value).strip()
        if text:
            self.rows.append((tab, line, name, text))

    def to_xml(self):
        out = ['  <CARD RTFDOC="1">' if self.primary else '  <CARD>', '   <FIELDS>']
        for tag, value in self.fields:
            text = '' if value is None or value is False else str(value)
            out.append(f'    <{tag}>{escape(text)}</{tag}>' if text else f'    <{tag} />')
        out.append('   </FIELDS>')
        out.append('   <DOCUMENT>')
        for tab, line, name, text in self.rows:
            out.append(
                f'    <ROW LINE="{line}" TAB="{tab}" NAME={quoteattr(name)}>'
                f'<VALUE>{escape(text)}</VALUE></ROW>')
        out.append('   </DOCUMENT>')
        out.append('  </CARD>')
        return '\n'.join(out)


def build_zvit(edrpou, cards, create_date):
    """Зібрати файл обміну та повернути його байти у windows-1251.

    Символи поза кодовою сторінкою (напр. «ʼ» U+02BC) йдуть числовими
    посиланнями ``&#NNN;`` — так XML лишається коректним і нічого не губиться.
    """
    parts = [
        f'<?xml version="1.0" encoding="{ENCODING}"?>',
        '<ZVIT>',
        ' <TRANSPORT>',
        f'  <VERSION>{ZVIT_VERSION}</VERSION>',
        f'  <CREATEDATE>{fmt_date(create_date)}</CREATEDATE>',
        ' </TRANSPORT>',
        ' <ORG>',
        '  <FIELDS>',
        f'   <EDRPOU>{escape(str(edrpou or ""))}</EDRPOU>',
        '  </FIELDS>',
    ]
    parts.extend(card.to_xml() for card in cards)
    parts.extend([' </ORG>', '</ZVIT>', ''])
    return '\n'.join(parts).encode(ENCODING, errors='xmlcharrefreplace')
