"""Ukrainian fixed assets (Основні засоби) — standalone model."""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class L10nUaAsset(models.Model):
    _name = 'l10n_ua.asset'
    _description = 'Основний засіб'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'acquisition_date desc, id desc'

    name = fields.Char(
        string='Найменування',
        required=True,
        tracking=True,
    )
    inventory_number = fields.Char(
        string='Інвентарний номер',
        tracking=True,
    )
    acquisition_date = fields.Date(
        string='Дата придбання',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    original_value = fields.Monetary(
        string='Первісна вартість',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    salvage_value = fields.Monetary(
        string='Ліквідаційна вартість',
        currency_field='currency_id',
        help='Очікувана вартість при вибутті',
    )

    # --- Classification ---
    group_id = fields.Many2one(
        'l10n_ua.asset.group',
        string='Група ОЗ',
        help='Група ОЗ згідно Податкового кодексу (1-16)',
    )

    # --- Depreciation parameters ---
    depreciation_method = fields.Selection(
        selection=[
            ('straight_line', 'Прямолінійний'),
            ('declining_balance', 'Зменшення залишку'),
            ('production', 'Виробничий'),
            ('cumulative', 'Кумулятивний'),
        ],
        string='Метод амортизації',
        default='straight_line',
        tracking=True,
    )
    useful_life = fields.Integer(
        string='Строк корисного використання (міс.)',
        help='Строк корисного використання у місяцях',
    )
    annual_depreciation_rate = fields.Float(
        string='Річна норма амортизації (%)',
        help='Для методу зменшення залишку. Якщо 0 — '
             'розраховується як 2/строк_років (подвійно-зменшуваний).',
    )
    production_capacity = fields.Float(
        string='Виробнича потужність',
        help='Загальна очікувана кількість одиниць продукції (для виробничого методу)',
    )
    produced_units = fields.Float(
        string='Вироблено одиниць',
        help='Кількість вироблених одиниць на поточний момент',
    )

    # --- State ---
    state = fields.Selection(
        selection=[
            ('draft', 'Чернетка'),
            ('open', 'В експлуатації'),
            ('paused', 'Призупинено'),
            ('close', 'Списано'),
        ],
        string='Стан',
        default='draft',
        tracking=True,
    )

    # --- Commissioning ---
    commission_date = fields.Date(
        string='Дата введення в експлуатацію',
        tracking=True,
    )
    commission_act_number = fields.Char(
        string='№ акту введення',
        copy=False,
    )
    responsible_id = fields.Many2one(
        'hr.employee',
        string='МВО',
        help='Матеріально відповідальна особа',
    )
    location = fields.Char(
        string='Місцезнаходження',
    )

    # --- Write-off ---
    writeoff_act_number = fields.Char(
        string='№ акту списання',
        copy=False,
    )
    writeoff_date = fields.Date(
        string='Дата списання',
    )
    writeoff_reason = fields.Text(
        string='Причина списання',
    )

    # --- Company / Currency ---
    company_id = fields.Many2one(
        'res.company',
        string='Компанія',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
    )

    # --- Depreciation board ---
    depreciation_line_ids = fields.One2many(
        'l10n_ua.asset.depreciation',
        'asset_id',
        string='Амортизаційні нарахування',
    )

    # --- Computed ---
    depreciation_amount = fields.Monetary(
        string='Місячна амортизація',
        compute='_compute_depreciation_amount',
        currency_field='currency_id',
        help='Місячна сума амортизації за обраним методом',
    )
    accumulated_depreciation = fields.Monetary(
        string='Накопичена амортизація',
        compute='_compute_accumulated_depreciation',
        store=True,
        currency_field='currency_id',
    )
    book_value = fields.Monetary(
        string='Залишкова вартість',
        compute='_compute_accumulated_depreciation',
        store=True,
        currency_field='currency_id',
    )

    notes = fields.Text(
        string='Примітки',
    )

    @api.onchange('group_id')
    def _onchange_group_id(self):
        if self.group_id and self.group_id.min_useful_life:
            self.useful_life = self.group_id.min_useful_life * 12

    # --- Depreciation computation ---

    @api.depends('original_value', 'salvage_value', 'useful_life',
                 'depreciation_method', 'annual_depreciation_rate',
                 'production_capacity', 'produced_units',
                 'depreciation_line_ids', 'depreciation_line_ids.state')
    def _compute_depreciation_amount(self):
        """Calculate monthly depreciation using Ukrainian methods."""
        for asset in self:
            amount = 0.0
            depreciable = asset.original_value - asset.salvage_value
            if depreciable <= 0 or not asset.useful_life:
                asset.depreciation_amount = 0
                continue

            if asset.depreciation_method == 'straight_line':
                amount = depreciable / asset.useful_life

            elif asset.depreciation_method == 'declining_balance':
                residual = depreciable
                if asset.id:
                    posted = sum(
                        asset.depreciation_line_ids.filtered(
                            lambda l: l.state == 'posted'
                        ).mapped('amount')
                    )
                    residual = max(0, depreciable - posted)
                if asset.annual_depreciation_rate:
                    annual_rate = asset.annual_depreciation_rate / 100
                else:
                    useful_years = asset.useful_life / 12
                    annual_rate = 2 / useful_years if useful_years else 0
                amount = residual * annual_rate / 12

            elif asset.depreciation_method == 'production':
                if asset.production_capacity:
                    amount = depreciable * (asset.produced_units / asset.production_capacity)
                else:
                    amount = 0

            elif asset.depreciation_method == 'cumulative':
                useful_years = asset.useful_life / 12
                if useful_years > 0:
                    months_elapsed = 0
                    if asset.id:
                        months_elapsed = len(
                            asset.depreciation_line_ids.filtered(
                                lambda l: l.state == 'posted'))
                    current_year = int(months_elapsed / 12) + 1
                    remaining_years = max(0, useful_years - current_year + 1)
                    sum_of_years = useful_years * (useful_years + 1) / 2
                    if sum_of_years:
                        annual_amount = depreciable * remaining_years / sum_of_years
                        amount = annual_amount / 12

            asset.depreciation_amount = round(amount, 2)

    @api.depends('depreciation_line_ids', 'depreciation_line_ids.state',
                 'depreciation_line_ids.amount', 'original_value')
    def _compute_accumulated_depreciation(self):
        for asset in self:
            posted = sum(
                asset.depreciation_line_ids.filtered(
                    lambda l: l.state == 'posted'
                ).mapped('amount')
            )
            asset.accumulated_depreciation = posted
            asset.book_value = asset.original_value - posted

    def _get_depreciation_amount(self, month_number):
        """Calculate depreciation for a specific month number (1-based)."""
        self.ensure_one()
        depreciable = self.original_value - self.salvage_value
        if depreciable <= 0 or not self.useful_life:
            return 0.0

        if self.depreciation_method == 'straight_line':
            return round(depreciable / self.useful_life, 2)

        elif self.depreciation_method == 'declining_balance':
            if self.annual_depreciation_rate:
                annual_rate = self.annual_depreciation_rate / 100
            else:
                useful_years = self.useful_life / 12
                annual_rate = 2 / useful_years if useful_years else 0
            monthly_rate = annual_rate / 12
            residual = depreciable
            for _i in range(month_number - 1):
                residual -= residual * monthly_rate
                if residual <= 0:
                    return 0.0
            return round(residual * monthly_rate, 2)

        elif self.depreciation_method == 'cumulative':
            useful_years = self.useful_life / 12
            if useful_years <= 0:
                return 0.0
            current_year = int((month_number - 1) / 12) + 1
            remaining_years = max(0, useful_years - current_year + 1)
            sum_of_years = useful_years * (useful_years + 1) / 2
            if not sum_of_years:
                return 0.0
            annual_amount = depreciable * remaining_years / sum_of_years
            return round(annual_amount / 12, 2)

        elif self.depreciation_method == 'production':
            if self.production_capacity:
                return round(
                    depreciable * (self.produced_units / self.production_capacity), 2
                )
            return 0.0

        return 0.0

    # --- State actions ---

    def action_commission(self):
        """Commission asset — put into operation."""
        for asset in self:
            vals = {'state': 'open'}
            if not asset.commission_date:
                vals['commission_date'] = fields.Date.context_today(self)
            if not asset.commission_act_number:
                vals['commission_act_number'] = self.env['ir.sequence'].next_by_code(
                    'l10n_ua.asset.commission.act'
                ) or _('New')
            asset.write(vals)

    def action_pause(self):
        """Pause depreciation."""
        self.write({'state': 'paused'})

    def action_resume(self):
        """Resume from paused state."""
        self.write({'state': 'open'})

    def action_write_off(self):
        """Write off asset."""
        for asset in self:
            vals = {'state': 'close'}
            if not asset.writeoff_date:
                vals['writeoff_date'] = fields.Date.context_today(self)
            if not asset.writeoff_act_number:
                vals['writeoff_act_number'] = self.env['ir.sequence'].next_by_code(
                    'l10n_ua.asset.writeoff.act'
                ) or _('New')
            asset.write(vals)

    def action_draft(self):
        """Return to draft."""
        self.write({
            'state': 'draft',
            'commission_date': False,
            'commission_act_number': False,
            'writeoff_date': False,
            'writeoff_act_number': False,
            'writeoff_reason': False,
        })

    def action_compute_depreciation(self):
        """Compute depreciation board for the useful life period."""
        DepLine = self.env['l10n_ua.asset.depreciation']
        for asset in self:
            if not asset.useful_life or not asset.original_value:
                raise UserError(_('Вкажіть первісну вартість та строк корисного використання.'))
            # Remove draft lines
            asset.depreciation_line_ids.filtered(lambda l: l.state == 'draft').unlink()
            # Determine start date
            start_date = asset.commission_date or asset.acquisition_date
            if not start_date:
                raise UserError(_('Вкажіть дату придбання або введення в експлуатацію.'))
            # Generate lines for remaining months
            posted_count = len(asset.depreciation_line_ids.filtered(lambda l: l.state == 'posted'))
            accumulated = sum(asset.depreciation_line_ids.filtered(lambda l: l.state == 'posted').mapped('amount'))
            depreciable = asset.original_value - asset.salvage_value

            for month_num in range(posted_count + 1, asset.useful_life + 1):
                amount = asset._get_depreciation_amount(month_num)
                if accumulated + amount > depreciable:
                    amount = max(0, depreciable - accumulated)
                if amount <= 0:
                    break
                accumulated += amount
                # Calculate date
                dt = start_date
                month = dt.month + (month_num - 1)
                year = dt.year + (month - 1) // 12
                month = (month - 1) % 12 + 1
                day = min(dt.day, 28)  # safe day
                line_date = dt.replace(year=year, month=month, day=day)

                DepLine.create({
                    'asset_id': asset.id,
                    'date': line_date,
                    'amount': amount,
                    'accumulated': accumulated,
                    'remaining': asset.original_value - accumulated,
                    'state': 'draft',
                })

    # --- Print actions ---

    def action_print_oz6(self):
        """Print OZ-6 Inventory Card."""
        self.ensure_one()
        return self.env.ref(
            'l10n_ua_assets.action_report_asset_oz6'
        ).report_action(self)

    def action_print_commission_act(self):
        """Print Commissioning Act."""
        self.ensure_one()
        if not self.commission_act_number:
            self.action_commission()
        return self.env.ref(
            'l10n_ua_assets.action_report_asset_commission'
        ).report_action(self)

    def action_print_writeoff_act(self):
        """Print Write-off Act."""
        self.ensure_one()
        if not self.writeoff_act_number:
            self.action_write_off()
        return self.env.ref(
            'l10n_ua_assets.action_report_asset_writeoff'
        ).report_action(self)

    # --- Helpers for reports ---

    def _get_depreciation_method_name(self):
        """Return Ukrainian name of depreciation method."""
        self.ensure_one()
        method_map = {
            'straight_line': 'Прямолінійний',
            'declining_balance': 'Зменшення залишкової вартості',
            'production': 'Виробничий',
            'cumulative': 'Кумулятивний',
        }
        return method_map.get(self.depreciation_method, '')

    def _get_group_name(self):
        """Return asset group display string."""
        self.ensure_one()
        if self.group_id:
            return '%s — %s' % (self.group_id.code, self.group_id.name)
        return ''


class L10nUaAssetDepreciation(models.Model):
    _name = 'l10n_ua.asset.depreciation'
    _description = 'Амортизаційне нарахування'
    _order = 'date, id'

    asset_id = fields.Many2one(
        'l10n_ua.asset',
        string='Основний засіб',
        required=True,
        ondelete='cascade',
    )
    date = fields.Date(
        string='Дата',
        required=True,
    )
    amount = fields.Monetary(
        string='Амортизація за період',
        currency_field='currency_id',
    )
    accumulated = fields.Monetary(
        string='Накопичена амортизація',
        currency_field='currency_id',
    )
    remaining = fields.Monetary(
        string='Залишкова вартість',
        currency_field='currency_id',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Чернетка'),
            ('posted', 'Проведено'),
        ],
        string='Стан',
        default='draft',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='asset_id.currency_id',
    )

    def action_post(self):
        """Post depreciation line."""
        self.write({'state': 'posted'})

    def action_draft(self):
        """Revert to draft."""
        self.write({'state': 'draft'})
