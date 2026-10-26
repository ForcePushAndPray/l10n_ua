from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# За скільки днів до закінчення договору ставити нагадування
EXPIRY_NOTICE_DAYS = 90


class AgroLandLease(models.Model):
    """Договір оренди землі (паю). Право оренди виникає з держреєстрації
    в ДРРП, тому номер запису й дата реєстрації — окремі поля."""
    _name = 'l10n_ua.agro.land.lease'
    _description = 'Land Lease Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, name'

    name = fields.Char(string='Contract Number', required=True, tracking=True, copy=False)
    date = fields.Date(string='Contract Date', default=fields.Date.context_today)
    lessor_id = fields.Many2one(
        'res.partner', string='Lessor', required=True, tracking=True, index=True)
    lessor_is_individual = fields.Boolean(
        compute='_compute_lessor_is_individual',
        help='Орендодавець — фізособа: орендар як податковий агент утримує ПДФО і ВЗ.')
    plot_ids = fields.Many2many(
        'l10n_ua.agro.land.plot', 'l10n_ua_agro_land_lease_plot_rel', 'lease_id', 'plot_id',
        string='Land Plots', required=True)
    plots_area = fields.Float(
        string='Area (ha)', digits=(16, 4), compute='_compute_plot_totals', store=True)
    ngo_total = fields.Monetary(
        string='Valuation of Plots', compute='_compute_plot_totals', store=True)
    date_start = fields.Date(string='Start Date', required=True, tracking=True)
    term_years = fields.Integer(string='Term (years)', default=7, tracking=True)
    date_end = fields.Date(
        string='End Date', compute='_compute_date_end', store=True, readonly=False,
        tracking=True)
    registration_date = fields.Date(
        string='Registration Date', tracking=True,
        help='Дата державної реєстрації права оренди в Державному реєстрі речових прав.')
    registration_number = fields.Char(
        string='Registration Record Number',
        help='Номер запису про інше речове право в ДРРП.')
    rent_method = fields.Selection([
        ('ngo_percent', '% of Valuation'),
        ('fixed', 'Fixed Amount'),
    ], string='Rent Calculation', required=True, default='ngo_percent', tracking=True)
    rent_percent = fields.Float(
        string='Rent (% of valuation)', digits=(5, 2), tracking=True)
    rent_fixed = fields.Monetary(string='Rent per Year', tracking=True)
    annual_rent = fields.Monetary(
        string='Annual Rent', compute='_compute_annual_rent', store=True,
        help='Річна орендна плата до утримання податків.')
    payment_form = fields.Selection([
        ('money', 'Money'),
        ('in_kind', 'In Kind'),
    ], string='Payment Form', required=True, default='money', tracking=True)
    in_kind_product_id = fields.Many2one(
        'product.product', string='In-kind Product',
        help='Продукція, якою зазвичай видають орендну плату (зерно, цукор).')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('terminated', 'Terminated'),
    ], default='draft', required=True, tracking=True, copy=False)
    expiry_notified = fields.Boolean(copy=False)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    accrual_line_ids = fields.One2many(
        'l10n_ua.agro.rent.accrual.line', 'lease_id', string='Rent Accruals')
    rent_residual = fields.Monetary(
        string='Rent Debt', compute='_compute_rent_residual',
        help='Нараховано, але ще не виплачено (після утримання податків).')
    note = fields.Text()

    @api.depends('lessor_id.is_company')
    def _compute_lessor_is_individual(self):
        for lease in self:
            lease.lessor_is_individual = bool(lease.lessor_id) and not lease.lessor_id.is_company

    @api.depends('plot_ids.area', 'plot_ids.ngo_value')
    def _compute_plot_totals(self):
        for lease in self:
            lease.plots_area = sum(lease.plot_ids.mapped('area'))
            lease.ngo_total = sum(lease.plot_ids.mapped('ngo_value'))

    @api.depends('date_start', 'term_years')
    def _compute_date_end(self):
        for lease in self:
            if lease.date_start and lease.term_years:
                lease.date_end = lease.date_start + relativedelta(
                    years=lease.term_years, days=-1)

    @api.depends('rent_method', 'rent_percent', 'rent_fixed', 'ngo_total')
    def _compute_annual_rent(self):
        for lease in self:
            if lease.rent_method == 'fixed':
                lease.annual_rent = lease.rent_fixed
            else:
                lease.annual_rent = lease.currency_id.round(
                    lease.ngo_total * lease.rent_percent / 100.0)

    @api.depends('accrual_line_ids.residual')
    def _compute_rent_residual(self):
        for lease in self:
            lease.rent_residual = sum(lease.accrual_line_ids.mapped('residual'))

    @api.depends('name', 'lessor_id')
    def _compute_display_name(self):
        for lease in self:
            lease.display_name = '%s (%s)' % (lease.name, lease.lessor_id.name) \
                if lease.lessor_id else lease.name

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for lease in self:
            if lease.date_end and lease.date_end < lease.date_start:
                raise ValidationError(self.env._('The lease cannot end before it starts.'))

    @api.constrains('state', 'plot_ids', 'date_start', 'date_end')
    def _check_plot_overlap(self):
        for lease in self.filtered(lambda l: l.state == 'active'):
            others = self.search([
                ('id', '!=', lease.id),
                ('state', '=', 'active'),
                ('plot_ids', 'in', lease.plot_ids.ids),
            ])
            for other in others:
                if lease._overlaps(other.date_start, other.date_end):
                    plots = lease.plot_ids & other.plot_ids
                    raise ValidationError(self.env._(
                        'Plot %(plots)s is already leased under contract %(contract)s '
                        'for the same period.',
                        plots=', '.join(plots.mapped('cadastral_number')),
                        contract=other.display_name))

    def _covers(self, on_date):
        self.ensure_one()
        return self.date_start <= on_date and (not self.date_end or on_date <= self.date_end)

    def _overlaps(self, date_from, date_to):
        """Чи перетинається строк договору з періодом [date_from, date_to]."""
        self.ensure_one()
        return (not date_to or self.date_start <= date_to) and \
            (not self.date_end or not date_from or self.date_end >= date_from)

    def _period_rent(self, date_from, date_to):
        """Орендна плата за період: річна плата пропорційно дням дії договору
        в періоді (рік — 365/366 днів року початку періоду)."""
        self.ensure_one()
        start = max(self.date_start, date_from)
        end = min(self.date_end, date_to) if self.date_end else date_to
        if end < start:
            return 0.0
        year_days = (date_from.replace(month=12, day=31) - date_from.replace(month=1, day=1)).days + 1
        days = (end - start).days + 1
        return self.currency_id.round(self.annual_rent * days / year_days)

    # --- Дії ---

    def action_activate(self):
        for lease in self:
            if not lease.plot_ids:
                raise UserError(self.env._('Add the leased land plots first.'))
            if not lease.annual_rent:
                raise UserError(self.env._('Set the rent of contract %s.', lease.name))
        self.write({'state': 'active'})

    def action_terminate(self):
        self.write({'state': 'terminated'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_renew(self):
        """Пролонгація на той самий строк з дня, наступного за закінченням."""
        for lease in self:
            if not lease.date_end or not lease.term_years:
                raise UserError(self.env._('Contract %s has no end date to renew from.', lease.name))
            lease.write({
                'date_end': lease.date_end + relativedelta(years=lease.term_years),
                'state': 'active',
                'expiry_notified': False,
            })
            lease.message_post(body=self.env._('Contract renewed until %s.', lease.date_end))

    @api.model
    def _cron_check_expiry(self):
        """Нагадування за 90 днів до закінчення і закриття прострочених договорів."""
        today = fields.Date.context_today(self)
        self.search([('state', '=', 'active'), ('date_end', '<', today)]).write(
            {'state': 'expired'})
        expiring = self.search([
            ('state', '=', 'active'),
            ('expiry_notified', '=', False),
            ('date_end', '<=', today + relativedelta(days=EXPIRY_NOTICE_DAYS)),
        ])
        for lease in expiring:
            lease.activity_schedule(
                'mail.mail_activity_data_todo',
                date_deadline=lease.date_end,
                summary=self.env._('Land lease expires'),
                note=self.env._(
                    'Contract %(contract)s with %(lessor)s expires on %(date)s: renew it or '
                    'return the plots.',
                    contract=lease.name, lessor=lease.lessor_id.name, date=lease.date_end),
                user_id=lease.create_uid.id or self.env.uid,
            )
        expiring.expiry_notified = True
