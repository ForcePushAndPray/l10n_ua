from odoo import api, fields, models


class L10nUaMarketplaceMixin(models.AbstractModel):
    _name = 'l10n_ua.marketplace.mixin'
    _description = 'Marketplace Mixin'

    marketplace_type = fields.Selection(
        selection=[],
        string='Marketplace Type',
    )

    def mp_sync_products(self):
        """Sync products to marketplace. Override in specific modules."""
        raise NotImplementedError()

    def mp_sync_stock(self):
        """Sync stock levels to marketplace. Override in specific modules."""
        raise NotImplementedError()

    def mp_sync_prices(self):
        """Sync prices to marketplace. Override in specific modules."""
        raise NotImplementedError()

    def mp_import_orders(self):
        """Import orders from marketplace. Override in specific modules."""
        raise NotImplementedError()

    def mp_update_order_status(self, order, status):
        """Update order status on marketplace. Override in specific modules."""
        raise NotImplementedError()
