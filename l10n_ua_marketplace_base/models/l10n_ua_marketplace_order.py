from odoo import api, fields, models


class L10nUaMarketplaceConfig(models.Model):
    _name = 'l10n_ua.marketplace.config'
    _description = 'Marketplace Configuration'
    _inherit = ['l10n_ua.marketplace.mixin', 'l10n_ua.feed.mixin']

    name = fields.Char(
        string='Name',
        required=True,
    )
    marketplace_type = fields.Selection(
        selection=[
            ('rozetka', 'Rozetka'),
            ('prom', 'Prom.ua'),
        ],
        string='Marketplace',
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(
        default=True,
    )
    
    # API settings
    api_url = fields.Char(
        string='API URL',
    )
    api_key = fields.Char(
        string='API Key',
    )
    
    # Feed settings
    feed_url = fields.Char(
        string='Feed URL',
        compute='_compute_feed_url',
    )
    auto_sync_stock = fields.Boolean(
        string='Auto Sync Stock',
        default=False,
    )
    auto_import_orders = fields.Boolean(
        string='Auto Import Orders',
        default=False,
    )
    sync_interval = fields.Integer(
        string='Sync Interval (hours)',
        default=1,
    )
    last_sync_date = fields.Datetime(
        string='Last Sync Date',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('active', 'Active'),
            ('error', 'Error'),
        ],
        string='State',
        default='draft',
    )

    def _compute_feed_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for config in self:
            config.feed_url = f'{base_url}/l10n_ua_marketplace/{config.marketplace_type}/feed/{config.id}'


class L10nUaMarketplaceOrder(models.Model):
    _name = 'l10n_ua.marketplace.order'
    _description = 'Marketplace Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='Order Reference',
        required=True,
    )
    marketplace_config_id = fields.Many2one(
        'l10n_ua.marketplace.config',
        string='Marketplace',
        required=True,
    )
    marketplace_type = fields.Selection(
        related='marketplace_config_id.marketplace_type',
        store=True,
    )
    external_id = fields.Char(
        string='External Order ID',
        index=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
    )
    order_date = fields.Datetime(
        string='Order Date',
    )
    state = fields.Selection(
        selection=[
            ('new', 'New'),
            ('processing', 'Processing'),
            ('shipped', 'Shipped'),
            ('delivered', 'Delivered'),
            ('cancelled', 'Cancelled'),
        ],
        string='State',
        default='new',
        tracking=True,
    )
    marketplace_state = fields.Char(
        string='Marketplace State',
    )
    total_amount = fields.Monetary(
        string='Total Amount',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )
    delivery_method = fields.Char(
        string='Delivery Method',
    )
    delivery_address = fields.Text(
        string='Delivery Address',
    )
    raw_data = fields.Text(
        string='Raw Data',
        help='Original order data from marketplace',
    )

    _unique_external_marketplace = models.Constraint(
        'UNIQUE(external_id, marketplace_config_id)',
        'External order ID must be unique per marketplace!',
    )

    def action_create_sale_order(self):
        """Create sale order from marketplace order."""
        self.ensure_one()
        # TODO: Implement sale order creation
        pass

    def action_sync_status(self):
        """Sync status with marketplace."""
        self.ensure_one()
        # TODO: Implement status sync
        pass
