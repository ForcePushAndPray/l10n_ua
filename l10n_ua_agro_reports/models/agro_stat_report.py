"""Статистична звітність сільськогосподарського підприємства: форми № 4-сг,
29-сг і 50-сг (річні). Коди рядків і графи — з бланків, див. stat_forms.

Кожна клітинка форми — рядок звіту. Обчислене з даних Odoo можна перекрити
вручну, і ручне значення переживає перерахунок; клітинки, для яких даних в
Odoo немає, від початку ручні. Форми подаються лише в «Кабінеті
респондента» Держстату (https://statzvit.ukrstat.gov.ua) з КЕП; файлового
формату для імпорту Держстат не публікує, тож звіт дає друковану форму й
XLSX для перенесення.
"""
import base64
import io
from collections import defaultdict
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_round

from .stat_forms import (
    COST_COLUMNS, COST_ROW_BY_CROP, COST_ROW_NAMES, CROP_ROWS, EXPENSE_ROWS, GRAIN_CODES, LAND_ROWS,
    MANUAL_COLUMNS, SECTIONS, STOCK_COLUMNS, STOCK_ROW_BY_CROP, STOCK_ROW_NAMES, TILLAGE_ROWS,
    UNIT_29_I, WINTER_ROWS,
)

FORMS = [
    ('4sg', '4-сг'),
    ('29sg', '29-сг'),
    ('50sg', '50-сг'),
]
UNIT_DIGITS = {'ha': 2, 'c': 1, 'kuah': 1}

# Вид витрат за рахунком-кореспондентом (найдовший префікс виграє)
COST_KIND_BY_ACCOUNT = [
    ('685', 'rent'),        # орендна плата за паї (нарахування оренди)
    ('66', 'labor'),
    ('65', 'social'),
    ('13', 'amortization'),
    ('63', 'services'),
    ('203', 'fuel'),
    ('20', 'material'),
    ('22', 'material'),
]
MATERIAL_KINDS = ('seed', 'fertilizer', 'fuel', 'material')


class AgroStatReport(models.Model):
    _name = 'l10n_ua.agro.stat.report'
    _description = 'Agricultural Statistical Report'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, form'

    name = fields.Char(compute='_compute_name', store=True)
    form = fields.Selection(FORMS, string='Form', required=True, default='29sg', tracking=True)
    year = fields.Integer(
        required=True, tracking=True, default=lambda self: fields.Date.context_today(self).year,
        help='4-сг — рік урожаю, під який посіяно; 29-сг і 50-сг — звітний рік.')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')], default='draft', required=True,
                             tracking=True, copy=False)
    date_deadline = fields.Date(string='Filing Deadline', compute='_compute_deadline', store=True)
    line_ids = fields.One2many('l10n_ua.agro.stat.report.line', 'report_id', string='Rows', copy=False)
    computed_on = fields.Datetime(string='Computed On', readonly=True, copy=False)
    warning = fields.Text(readonly=True, copy=False)
    notes = fields.Text()

    _form_year_company_uniq = models.Constraint(
        'UNIQUE(form, year, company_id)',
        'A report of this form for this year already exists.',
    )

    @api.depends('form', 'year')
    def _compute_name(self):
        labels = dict(FORMS)
        for rec in self:
            if rec.form == '4sg':
                rec.name = '%s під урожай %s року' % (labels[rec.form], rec.year)
            else:
                rec.name = '%s за %s рік' % (labels.get(rec.form, ''), rec.year)

    @api.depends('form', 'year')
    def _compute_deadline(self):
        for rec in self:
            if not rec.year:
                rec.date_deadline = False
            elif rec.form == '4sg':
                rec.date_deadline = date(rec.year, 6, 2)
            elif rec.form == '29sg':
                rec.date_deadline = date(rec.year + 1, 1, 11)
            else:
                rec.date_deadline = date(rec.year + 1, 2, 28)

    # ------------------------------------------------------------------ rows

    def _line(self, section, code, column='1'):
        self.ensure_one()
        return self.line_ids.filtered(
            lambda l: l.section == section and l.code == code and l.column_no == column)[:1]

    def get_value(self, section, code, column='1'):
        """Значення клітинки, як її подано (з ручним перекриттям)."""
        return self._line(section, code, column).value

    def _section_unit(self, section, column):
        if self.form == '29sg' and section == 'I':
            return UNIT_29_I[column]
        return SECTIONS[self.form][section][1]

    def _row_defs(self, raw):
        """Рядки форми: (розділ, код, назва). Розділи з переліком культур
        містять лише культури, для яких є дані або введене вручну."""
        self.ensure_one()
        kept = {(l.section, l.code) for l in self.line_ids if l.is_manual}
        with_data = {(section, code) for (section, code, _col) in raw}

        def present(section, codes):
            return [code for code in codes if (section, code) in with_data | kept]

        rows = []
        if self.form == '4sg':
            rows += [('I', code, CROP_ROWS[code]) for code in present('I', CROP_ROWS)]
            rows += [('II', code, name) for code, name in LAND_ROWS]
        elif self.form == '29sg':
            rows += [('I', code, CROP_ROWS[code]) for code in present('I', CROP_ROWS)]
            rows += [('VI', code, name) for code, name in sorted(WINTER_ROWS.values())]
            rows += [('VII', code, name) for code, name in TILLAGE_ROWS]
        else:
            totals = ('1101', '1102')
            rows += [('I', code, COST_ROW_NAMES[code]) for code in totals]
            rows += [('I', code, COST_ROW_NAMES[code])
                     for code in present('I', [c for c in COST_ROW_NAMES if c not in totals])]
            rows += [('II', code, name) for code, name, _kind in EXPENSE_ROWS]
            rows += [('III', '3001', STOCK_ROW_NAMES['3001'])]
            rows += [('III', code, STOCK_ROW_NAMES[code])
                     for code in present('III', [c for c in STOCK_ROW_NAMES if c != '3001'])]
        return rows

    def _sync_lines(self, raw):
        """Привести рядки звіту у відповідність до форми, зберігши введене."""
        for rec in self:
            existing = {(l.section, l.code, l.column_no): l for l in rec.line_ids}
            wanted = set()
            vals = []
            for seq, (section, code, name) in enumerate(rec._row_defs(raw)):
                manual_columns = MANUAL_COLUMNS.get((rec.form, section), set())
                for column in SECTIONS[rec.form][section][2]:
                    key = (section, code, column)
                    wanted.add(key)
                    auto = column not in manual_columns and not rec._is_manual_row(section, code)
                    line = existing.get(key)
                    if line:
                        line.sequence = seq
                        continue
                    vals.append({
                        'report_id': rec.id, 'sequence': seq, 'section': section, 'code': code,
                        'column_no': column, 'name': name, 'unit': rec._section_unit(section, column),
                        'is_auto': auto, 'is_manual': not auto,
                    })
            self.env['l10n_ua.agro.stat.report.line'].create(vals)
            rec.line_ids.filtered(lambda l: (l.section, l.code, l.column_no) not in wanted).unlink()

    def _is_manual_row(self, section, code):
        if self.form == '29sg' and section == 'VII':
            return True
        if self.form == '50sg' and section == 'II':
            return not dict((c, kind) for c, _n, kind in EXPENSE_ROWS)[code]
        if self.form == '4sg' and section == 'II':
            return code == '10310'
        return False

    # --------------------------------------------------------------- actions

    def action_compute(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(self.env._('Only a draft report can be recomputed.'))
            warnings = []
            raw = getattr(rec, '_compute_%s' % rec.form)(warnings)
            rec._sync_lines(raw)
            for line in rec.line_ids.filtered('is_auto'):
                line.computed_value = line._to_form_units(raw.get((line.section, line.code, line.column_no), 0.0))
            rec._compute_totals()
            rec.write({'computed_on': fields.Datetime.now(), 'warning': '\n'.join(warnings) or False})
        return True

    def _compute_totals(self):
        """Підсумкові рядки — сума складових, як їх подано (з ручними правками)."""
        self.ensure_one()

        def put(section, code, column, value):
            line = self._line(section, code, column)
            if line and line.is_auto:
                line.computed_value = float_round(value, precision_digits=UNIT_DIGITS[line.unit])

        if self.form == '4sg':
            for column in ('1', '2', '3'):
                put('II', '10000', column, sum(self.get_value('II', code, column)
                                               for code in ('10100', '10200', '10300', '10400')))
        elif self.form == '50sg':
            for code in {l.code for l in self.line_ids if l.section == 'I'}:
                get = lambda column: self.get_value('I', code, column)  # noqa: E731
                put('I', code, '2', sum(get(c) for c in ('3', '4', '5', '6')))
                put('I', code, '8', sum(get(c) for c in ('9', '10', '11', '12')))
                put('I', code, '1', sum(get(c) for c in ('2', '7', '8')))

    def action_done(self):
        for rec in self:
            if not rec.computed_on:
                raise UserError(self.env._('Compute the report before marking it as done.'))
        self.write({'state': 'done'})
        return True

    def action_draft(self):
        self.write({'state': 'draft'})
        return True

    def action_print(self):
        self.ensure_one()
        return self.env.ref('l10n_ua_agro_reports.action_report_agro_stat').report_action(self)

    # ------------------------------------------------------------ data helpers

    def _crop_code(self, crop, warnings):
        code = crop.l10n_ua_stat_code
        if not code:
            message = self.env._('Crop «%s» has no Derzhstat row code: it is left out of the report.', crop.name)
            if message not in warnings:
                warnings.append(message)
        return code

    def _plantings(self, year):
        return self.env['l10n_ua.agro.planting'].search([
            ('company_id', '=', self.company_id.id), ('season_id.year', '=', year)])

    # --------------------------------------------------------------- 4-сг

    def _compute_4sg(self, warnings):
        raw = defaultdict(float)
        for planting in self._plantings(self.year):
            code = self._crop_code(planting.crop_id, warnings)
            if code:
                raw[('I', code, '1')] += planting.area
        land_rows = {'arable': ('10100',), 'fallow': ('10100', '10110'), 'hayfield': ('10200',),
                     'pasture': ('10300',), 'perennial': ('10400',)}
        for field in self.env['l10n_ua.agro.field'].search([('company_id', '=', self.company_id.id)]):
            for code in land_rows.get(field.land_type, ()):
                raw[('II', code, '1')] += field.area
        return raw

    # -------------------------------------------------------------- 29-сг

    def _compute_29sg(self, warnings):
        raw = defaultdict(float)
        for planting in self._plantings(self.year):
            code = self._crop_code(planting.crop_id, warnings)
            if code and planting.harvest_weight:
                raw[('I', code, '1')] += planting.area
                raw[('I', code, '2')] += planting.harvest_weight * 10.0      # т → ц
        for planting in self._plantings(self.year + 1):
            code = self._crop_code(planting.crop_id, warnings)
            if code in WINTER_ROWS:
                raw[('VI', WINTER_ROWS[code][0], '1')] += planting.area
        return raw

    # -------------------------------------------------------------- 50-сг

    def _compute_50sg(self, warnings):
        raw = defaultdict(float)
        self._compute_50sg_costs(raw, warnings)
        self._compute_50sg_expenses(raw)
        self._compute_50sg_stock(raw, warnings)
        return raw

    def _cost_kind(self, line, cache):
        """Вид витрат рядка проводки: за видом агроматеріалу товару, інакше
        за рахунком-кореспондентом (найбільший рядок з протилежним знаком)."""
        product = line.product_id
        material_type = product.l10n_ua_agro_material_type
        if material_type in ('seed', 'fertilizer', 'fuel'):
            return material_type
        if material_type:
            return 'material'
        if product:
            # вид не вказано — за рахунком запасу товару (203 — паливо)
            kind = self._kind_by_account(product.categ_id.property_stock_valuation_account_id)
            if kind in ('fuel', 'material'):
                return kind
        move = line.move_id
        if move.id not in cache:
            cache[move.id] = {}
        key = line.balance > 0
        if key not in cache[move.id]:
            counter = move.line_ids.filtered(lambda l: (l.balance > 0) != key and l.balance)
            account = max(counter, key=lambda l: abs(l.balance)).account_id if counter else line.account_id
            cache[move.id][key] = self._kind_by_account(account)
        return cache[move.id][key]

    @staticmethod
    def _kind_by_account(account):
        for prefix, kind in COST_KIND_BY_ACCOUNT:
            if account.code and account.code.startswith(prefix):
                return kind
        return 'other'

    def _kinds(self, lines, cache):
        result = defaultdict(float)
        for line in lines:
            result[self._cost_kind(line, cache)] += line.balance
        return result

    def _harvest_moves(self):
        receipts = self.env['l10n_ua.agro.harvest.receipt'].search([
            ('company_id', '=', self.company_id.id), ('account_move_id', '!=', False)])
        return receipts.account_move_id | receipts.account_move_id.reversal_move_ids

    def _compute_50sg_costs(self, raw, warnings):
        """Розділ І: собівартість продукції, виробленої у звітному році, — з
        проведених калькуляцій сезону цього року, розкладена на статті так
        само, як калькуляція розподіляє непрямі й загальновиробничі витрати."""
        AML = self.env['account.move.line']
        calcs = self.env['l10n_ua.agro.cost.calculation'].search([
            ('company_id', '=', self.company_id.id), ('state', '=', 'posted'),
            ('season_id.year', '=', self.year)])
        if not calcs:
            warnings.append(self.env._(
                'No posted crop cost calculation for the %s season: section I has no production cost.', self.year))
        harvest_moves = self._harvest_moves()
        cache = {}
        products = {}
        for calc in calcs:
            account = calc._production_account()
            base = calc._base_domain(account) + [('move_id', 'not in', harvest_moves.ids)]
            direct = defaultdict(lambda: defaultdict(float))
            for line in AML.search(base + [('l10n_ua_agro_planting_id', '!=', False)]):
                direct[line.l10n_ua_agro_planting_id][self._cost_kind(line, cache)] += line.balance
            indirect = self._kinds(AML.search(base + [('l10n_ua_agro_planting_id', '=', False)]), cache)
            overhead = defaultdict(float)
            overhead_account = calc._overhead_account()
            if calc.include_overhead and overhead_account:
                for kind, amount in self._kinds(AML.search(calc._base_domain(overhead_account)), cache).items():
                    # прямих статей у загальновиробничих немає — це «решта»
                    overhead[kind if kind in ('social', 'amortization', 'services') else 'other'] += amount
            for calc_line in calc.line_ids.filtered(lambda l: not l.is_wip):
                planting = calc_line.planting_id
                code = self._crop_code(planting.crop_id, warnings)
                if not code:
                    continue
                if planting.crop_id.product_id:
                    products[planting.crop_id.product_id] = code
                kinds = defaultdict(float, direct.get(planting, {}))
                if calc.indirect_amount:
                    for kind, amount in indirect.items():
                        kinds[kind] += amount * calc_line.allocated_cost / calc.indirect_amount
                if calc.overhead_amount:
                    for kind, amount in overhead.items():
                        kinds[kind] += amount * calc_line.overhead_cost / calc.overhead_amount
                columns = {
                    '3': kinds['seed'], '4': kinds['fertilizer'], '5': kinds['fuel'], '6': kinds['material'],
                    '7': kinds['labor'], '9': kinds['social'], '10': kinds['amortization'],
                    '11': kinds['services'], '12': kinds['rent'] + kinds['other'],
                }
                for row in self._cost_rows(code):
                    for column, amount in columns.items():
                        raw[('I', row, column)] += amount
        # графа 13: собівартість реалізованої продукції за рік
        if products:
            sold = AML._read_group([
                ('company_id', '=', self.company_id.id), ('parent_state', '=', 'posted'),
                ('account_id.code', '=like', '90%'),
                ('date', '>=', date(self.year, 1, 1)), ('date', '<=', date(self.year, 12, 31)),
                ('product_id', 'in', [p.id for p in products])], ['product_id'], ['balance:sum'])
            for product, balance in sold:
                for row in self._cost_rows(products[product]):
                    raw[('I', row, '13')] += balance

    def _cost_rows(self, code):
        rows = ['1101']
        if code in GRAIN_CODES:
            rows.append('1102')
        if code in COST_ROW_BY_CROP:
            rows.append(COST_ROW_BY_CROP[code])
        return rows

    def _compute_50sg_expenses(self, raw):
        """Розділ ІІ: витрати рослинництва за календарний рік — рахунок 23 (без
        оцінки врожаю й закриття калькуляцій) і загальновиробничі 91."""
        AML = self.env['account.move.line']
        company = self.company_id
        common = [
            ('company_id', '=', company.id), ('parent_state', '=', 'posted'),
            ('date', '>=', date(self.year, 1, 1)), ('date', '<=', date(self.year, 12, 31)),
            ('move_id.l10n_ua_agro_calculation_id', '=', False),
        ]
        cache = {}
        production = company._l10n_ua_agro_ops_account('l10n_ua_agro_production_account_id', ('231', '23'))
        kinds = defaultdict(float)
        if production:
            kinds = self._kinds(AML.search(common + [
                ('account_id', '=', production.id), ('move_id', 'not in', self._harvest_moves().ids)]), cache)
        overhead_account = company._l10n_ua_agro_ops_account('l10n_ua_agro_overhead_account_id', ('91',))
        overhead = self._kinds(AML.search(common + [('account_id', '=', overhead_account.id)]), cache) \
            if overhead_account else {}
        values = {
            'materials': sum(kinds[k] for k in MATERIAL_KINDS),
            'seed': kinds['seed'], 'fertilizer': kinds['fertilizer'], 'fuel': kinds['fuel'],
            'labor': kinds['labor'],
            'other_direct': sum(kinds[k] for k in ('social', 'rent', 'amortization', 'services', 'other')),
            'social': kinds['social'], 'rent': kinds['rent'], 'amortization': kinds['amortization'],
            'overhead': sum(overhead.values()), 'overhead_services': overhead.get('services', 0.0),
        }
        for code, _name, kind in EXPENSE_ROWS:
            if kind:
                raw[('II', code, '1')] = values[kind]

    def _compute_50sg_stock(self, raw, warnings):
        """Розділ ІІІ: запаси й рух продукції рослинництва в центнерах — зі
        складських переміщень основної продукції культур."""
        crops = self.env['l10n_ua.agro.crop'].search([('product_id', '!=', False)])
        row_by_product = {}
        for crop in crops:
            code = crop.l10n_ua_stat_code
            if code in STOCK_ROW_BY_CROP:
                row_by_product[crop.product_id] = (STOCK_ROW_BY_CROP[code], code in GRAIN_CODES)
        if not row_by_product:
            return
        kg = self.env.ref('uom.product_uom_kgm')
        start = date(self.year, 1, 1)
        moves = self.env['stock.move'].search([
            ('company_id', '=', self.company_id.id), ('state', '=', 'done'),
            ('product_id', 'in', [p.id for p in row_by_product]),
            ('date', '<', fields.Datetime.to_datetime(date(self.year + 1, 1, 1)))])
        for move in moves:
            row, grain = row_by_product[move.product_id]
            uom = move.product_id.uom_id
            if not uom._has_common_reference(kg):
                message = self.env._('Product «%s» is not measured by weight: left out of section III.',
                                     move.product_id.display_name)
                if message not in warnings:
                    warnings.append(message)
                continue
            quantity = uom._compute_quantity(move.product_qty, kg, round=False) / 100.0
            src_internal = move.location_id.usage == 'internal'
            dest_internal = move.location_dest_id.usage == 'internal'
            if src_internal == dest_internal:
                continue
            columns = []
            if move.date.date() < start:
                columns.append(('1', quantity if dest_internal else -quantity))
            elif dest_internal:
                columns.append(('2', quantity))
                if move.location_id.usage == 'supplier':
                    columns.append(('3', quantity))
            else:
                columns.append(('4', quantity))
                column = self._disposal_column(move)
                if column:
                    columns.append((column, quantity))
            for column, value in columns:
                raw[('III', row, column)] += value
                if grain:
                    raw[('III', '3001', column)] += value

    def _disposal_column(self, move):
        """Графа розділу ІІІ, у яку потрапляє вибуття (None — лише графа 4)."""
        dest = move.location_dest_id
        if move.picking_id.l10n_ua_agro_rent_payment_id:
            return '8'
        if move.l10n_ua_agro_work_order_id:
            return '10'
        if dest.usage == 'inventory':
            return '11'
        if dest.usage == 'production':
            return '6'
        if dest.usage == 'customer':
            partner = (move.picking_id.partner_id or move.partner_id).commercial_partner_id
            if partner.l10n_ua_agro_processor:
                return '5'
            if partner and not partner.is_company:
                return '7'
        return None

    # ----------------------------------------------------------------- export

    def _sections(self):
        """Рядки звіту так, як їх розкладає форма: [{title, columns, rows}]."""
        self.ensure_one()
        result = []
        for section, (title, _unit, columns) in SECTIONS[self.form].items():
            lines = self.line_ids.filtered(lambda l: l.section == section).sorted('sequence')
            if not lines:
                continue
            rows = []
            for line in lines:
                if not rows or rows[-1]['code'] != line.code:
                    rows.append({'code': line.code, 'name': line.name, 'cells': {}})
                rows[-1]['cells'][line.column_no] = line
            result.append({'title': title, 'columns': list(columns.items()), 'rows': rows})
        return result

    def action_export_xlsx(self):
        """Рядки форми таблицею — для перенесення в «Кабінет респондента»."""
        self.ensure_one()
        try:
            import xlsxwriter
        except ImportError:
            raise UserError(self.env._('xlsxwriter is not installed. Run: pip install xlsxwriter'))
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet(dict(FORMS)[self.form])
        bold = workbook.add_format({'bold': True})
        wrap = workbook.add_format({'text_wrap': True, 'valign': 'top'})
        head = workbook.add_format({'bold': True, 'text_wrap': True, 'border': 1, 'valign': 'top'})
        formats = {unit: workbook.add_format({'num_format': '0.' + '0' * digits})
                   for unit, digits in UNIT_DIGITS.items()}
        sheet.set_column(0, 0, 55)
        sheet.set_column(1, 1, 8)
        sheet.set_column(2, 16, 14)
        sheet.write(0, 0, '%s — %s' % (self.name, self.company_id.name), bold)
        sheet.write(1, 0, self.env._('EDRPOU: %s', self.company_id.edrpou or ''))
        row = 3
        for section in self._sections():
            sheet.write(row, 0, section['title'], bold)
            row += 1
            sheet.write(row, 0, 'Назва', head)
            sheet.write(row, 1, 'Код рядка', head)
            for index, (column, label) in enumerate(section['columns']):
                sheet.write(row, 2 + index, '%s. %s' % (column, label), head)
            row += 1
            for form_row in section['rows']:
                sheet.write(row, 0, form_row['name'], wrap)
                sheet.write(row, 1, form_row['code'])
                for index, (column, _label) in enumerate(section['columns']):
                    line = form_row['cells'].get(column)
                    if line:
                        sheet.write_number(row, 2 + index, line.value, formats[line.unit])
                row += 1
            row += 1
        workbook.close()
        filename = '%s_%s_%s.xlsx' % (dict(FORMS)[self.form], self.company_id.edrpou or self.company_id.id,
                                      self.year)
        attachment = self.env['ir.attachment'].create({
            'name': filename, 'type': 'binary', 'datas': base64.b64encode(output.getvalue()),
            'res_model': self._name, 'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {'type': 'ir.actions.act_url', 'url': '/web/content/%s?download=true' % attachment.id,
                'target': 'self'}


class AgroStatReportLine(models.Model):
    _name = 'l10n_ua.agro.stat.report.line'
    _description = 'Agricultural Statistical Report Cell'
    _order = 'report_id, sequence, section, code, id'

    report_id = fields.Many2one('l10n_ua.agro.stat.report', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='report_id.company_id', store=True)
    report_state = fields.Selection(related='report_id.state')
    sequence = fields.Integer()
    section = fields.Char(required=True)
    code = fields.Char(string='Row Code', required=True)
    column_no = fields.Char(string='Column', required=True)
    column_label = fields.Char(string='Column Name', compute='_compute_column_label')
    name = fields.Char(string='Indicator', required=True)
    unit = fields.Selection([('ha', 'ha'), ('c', 'Quintals'), ('kuah', 'Thousand UAH')], required=True)
    is_auto = fields.Boolean(
        string='Computed', readonly=True,
        help='Odoo computes this cell. Cells it has no data for are entered by hand.')
    computed_value = fields.Float(string='Computed Value', digits=(16, 2), readonly=True)
    is_manual = fields.Boolean(
        string='Manual',
        help='Report the value entered by hand instead of the computed one. '
             'The value is kept when the report is recomputed.')
    manual_value = fields.Float(string='Manual Value', digits=(16, 2))
    value = fields.Float(string='Value', digits=(16, 2), compute='_compute_value', store=True)

    _report_cell_uniq = models.Constraint(
        'unique(report_id, section, code, column_no)',
        'A cell of the report can only appear once.',
    )

    @api.depends('report_id.form', 'section', 'column_no')
    def _compute_column_label(self):
        for line in self:
            section = SECTIONS.get(line.report_id.form, {}).get(line.section)
            line.column_label = section[2].get(line.column_no, line.column_no) if section else line.column_no

    @api.depends('is_manual', 'manual_value', 'computed_value', 'unit')
    def _compute_value(self):
        for line in self:
            value = line.manual_value if line.is_manual else line.computed_value
            line.value = float_round(value, precision_digits=UNIT_DIGITS.get(line.unit, 2))

    def _to_form_units(self, value):
        self.ensure_one()
        if self.unit == 'kuah':
            value = value / 1000.0
        return float_round(value or 0.0, precision_digits=UNIT_DIGITS[self.unit], rounding_method='HALF-UP')

    @api.onchange('is_manual')
    def _onchange_is_manual(self):
        if self.is_manual and not self.manual_value:
            self.manual_value = self.computed_value

    def write(self, vals):
        if any(line.report_id.state == 'done' for line in self) and set(vals) & {'is_manual', 'manual_value'}:
            raise UserError(self.env._('Reset the report to draft to change its rows.'))
        return super().write(vals)


class AgroCrop(models.Model):
    _inherit = 'l10n_ua.agro.crop'

    l10n_ua_stat_code = fields.Selection(
        [(code, '%s %s' % (code, name)) for code, name in CROP_ROWS.items()],
        string='Derzhstat Row Code',
        help='Код рядка культури у формах № 4-сг і 29-сг (наказ Держстату від 19.03.2026 № 69). '
             'Визначає й вид продукції у формі № 50-сг.')

    @api.model
    def _l10n_ua_fill_stat_codes(self):
        codes = {
            'crop_wheat_winter': '0070', 'crop_wheat_spring': '0100', 'crop_barley_winter': '0130',
            'crop_barley_spring': '0140', 'crop_rye': '0160', 'crop_oats': '0210', 'crop_corn': '0110',
            'crop_buckwheat': '0220', 'crop_sunflower': '0520', 'crop_rapeseed_winter': '0490',
            'crop_pumpkin_seed': '0597', 'crop_soybean': '0410', 'crop_pea': '0320',
            'crop_sugar_beet': '0750', 'crop_potato': '1250', 'crop_perennial_grass': '2260',
        }
        for xmlid, code in codes.items():
            crop = self.env.ref('l10n_ua_agro_base.%s' % xmlid, raise_if_not_found=False)
            if crop and not crop.l10n_ua_stat_code:
                crop.l10n_ua_stat_code = code


class ResPartner(models.Model):
    _inherit = 'res.partner'

    l10n_ua_agro_processor = fields.Boolean(
        string='Processing Enterprise',
        help='Покупець переробляє продукцію сам (елеватор-переробник, олійноекстракційний, '
             'цукровий завод тощо): продаж йому — графа 5 розділу ІІІ форми № 50-сг.')
