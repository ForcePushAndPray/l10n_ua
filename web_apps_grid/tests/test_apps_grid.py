from odoo.tests import HttpCase, tagged

from odoo.addons.web.tests.test_js import unit_test_error_checker


def _hoot_id(descriptor):
    # Same hash HOOT uses for suite/test ids (see web/tests/test_js.py).
    value = 0
    for char in descriptor:
        value = ((value << 5) - value + ord(char)) & 0xFFFFFFFF
    return f'{value:08x}'


@tagged('post_install', '-at_install')
class TestAppsGridJs(HttpCase):

    def test_apps_grid_hoot(self):
        self.browser_js(
            '/web/tests?headless&loglevel=2&preset=desktop&timeout=15000'
            f'&id={_hoot_id("@web_apps_grid")}',
            '', '', login='admin', timeout=600,
            success_signal='[HOOT] Test suite succeeded',
            error_checker=unit_test_error_checker,
        )
