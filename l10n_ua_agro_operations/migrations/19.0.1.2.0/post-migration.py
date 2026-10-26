"""Техкарти, що існували до появи затвердження (#482), уже працювали як
чинні: наряди брали з них норми. Нове поле стану заповнюється «Чернеткою»,
тож при оновленні позначаємо всі наявні карти затвердженими — інакше
«Заповнити за нормами» перестане їх бачити."""


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE l10n_ua_agro_tech_card
           SET state = 'approved', approved_date = write_date::date
         WHERE state = 'draft' AND approved_by_id IS NULL
    """)
