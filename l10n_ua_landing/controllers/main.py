from odoo import http
from odoo.http import request
from odoo.addons.website.controllers.main import Website


class WebsiteLanding(Website):
    """Віддаємо власний лендинг на / замість дефолтної сторінки Odoo Website.

    Внутрішні користувачі (кадровик, бухгалтер, адмін) одразу потрапляють у
    бекенд /odoo — їм маркетинговий лендинг не потрібен. Публічні відвідувачі
    бачать презентабельну сторінку без website-хедера/футера.
    """

    @http.route()
    def index(self, **kw):
        if request.env.user._is_internal():
            return request.redirect('/odoo')
        html = request.env['ir.qweb']._render('l10n_ua_landing.landing_page')
        return request.make_response(
            '<!DOCTYPE html>\n' + str(html),
            headers=[('Content-Type', 'text/html; charset=utf-8')],
        )
