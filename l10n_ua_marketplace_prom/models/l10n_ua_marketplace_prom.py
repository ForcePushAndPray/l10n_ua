from odoo import api, fields, models


class L10nUaMarketplaceConfig(models.Model):
    _inherit = 'l10n_ua.marketplace.config'

    prom_api_url = fields.Char(
        string='Prom API URL',
        default='https://my.prom.ua/api/v1/',
    )

    def prom_generate_feed(self):
        """Generate feed for Prom.ua."""
        self.ensure_one()
        products = self.env['product.template'].search([
            ('marketplace_publish', '=', True),
            ('marketplace_ids', 'in', self.id),
        ])
        return self.generate_yml_feed(products)

    def prom_sync_products(self):
        """Sync products to Prom.ua via API."""
        self.ensure_one()
        # TODO: Implement product sync
        pass

    def prom_sync_stock(self):
        """Sync stock to Prom.ua."""
        self.ensure_one()
        # TODO: Implement stock sync
        pass

    def prom_import_orders(self):
        """Import orders from Prom.ua."""
        self.ensure_one()
        # TODO: Implement order import
        pass

    def prom_update_order_status(self, order, status):
        """Update order status on Prom.ua."""
        self.ensure_one()
        # TODO: Implement status update
        pass
