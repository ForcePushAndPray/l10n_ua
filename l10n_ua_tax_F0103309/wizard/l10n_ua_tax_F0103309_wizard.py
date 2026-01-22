import logging
from datetime import date

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class L10nUaTaxDocumentWizardF0103309(models.TransientModel):
    """
    Extension of base tax document wizard for F0103309 (Single Tax Declaration).

    This is the "Декларація платника єдиного податку" form version 9.
    """
    _inherit = 'l10n_ua.tax.document.wizard'

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        # Get company from context or default
        company_id = res.get('company_id') or self.env.company.id
        company = self.env['res.company'].browse(company_id)

        if company:
            # Tax office
            if company.l10n_ua_tax_office_id:
                res['tax_office_id'] = company.l10n_ua_tax_office_id.id

            # FOP settings
            if company.l10n_ua_fop_group:
                res['fop_group'] = company.l10n_ua_fop_group
            if company.l10n_ua_tax_rate:
                res['tax_rate'] = company.l10n_ua_tax_rate

            # Activity codes (KVED) - fill from company settings
            if company.l10n_ua_kved_ids and 'activity_ids' in fields_list:
                activity_vals = []
                for company_kved in company.l10n_ua_kved_ids:
                    activity_vals.append((0, 0, {
                        'kved_id': company_kved.kved_id.id,
                        'is_primary': company_kved.is_primary,
                    }))
                if activity_vals:
                    res['activity_ids'] = activity_vals

        return res

    # F0103309 specific fields
    fop_group = fields.Selection(
        selection=[
            ('1', 'Group 1'),
            ('2', 'Group 2'),
            ('3', 'Group 3'),
        ],
        string='FOP Group',
        default='3',
    )
    tax_rate = fields.Float(
        string='Tax Rate (%)',
        default=5.0,
        help='Single tax rate: 5% for Group 3 (standard), 2% for e-residents, etc.',
    )
    declaration_type = fields.Selection(
        selection=[
            ('00', 'Reporting'),
            ('01', 'New Reporting'),
            ('02', 'Clarifying'),
        ],
        string='Declaration Type',
        default='00',
    )

    # Tax authority info
    tax_office_id = fields.Many2one(
        'l10n_ua.tax.office',
        string='Tax Office',
        domain=[('office_type', '=', 'district')],
    )

    # Income fields (Section 5)
    income_q1 = fields.Float(string='Q1 Income', digits=(16, 2))
    income_q2 = fields.Float(string='Q2 Income', digits=(16, 2))
    income_q3 = fields.Float(string='Q3 Income', digits=(16, 2))
    income_q4 = fields.Float(string='Q4 Income', digits=(16, 2))
    income_total = fields.Float(
        string='Total Income',
        compute='_compute_income_total',
        store=True,
        digits=(16, 2),
    )

    # Tax fields (Section 6)
    tax_q1 = fields.Float(string='Q1 Tax', digits=(16, 2))
    tax_q2 = fields.Float(string='Q2 Tax', digits=(16, 2))
    tax_q3 = fields.Float(string='Q3 Tax', digits=(16, 2))
    tax_q4 = fields.Float(string='Q4 Tax', digits=(16, 2))
    tax_total = fields.Float(
        string='Total Tax',
        compute='_compute_tax_total',
        store=True,
        digits=(16, 2),
    )

    # ESV fields (Section 8)
    esv_base = fields.Float(string='ESV Base', digits=(16, 2))
    esv_rate = fields.Float(string='ESV Rate (%)', default=22.0)
    esv_amount = fields.Float(
        string='ESV Amount',
        compute='_compute_esv_amount',
        store=True,
        digits=(16, 2),
    )

    # Activity codes (KVED)
    activity_ids = fields.One2many(
        'l10n_ua.tax.document.wizard.activity',
        'wizard_id',
        string='Activity Codes',
    )

    # Employment info
    has_employees = fields.Boolean(string='Has Employees', default=False)
    employee_count = fields.Integer(string='Employee Count', default=0)

    @api.depends('income_q1', 'income_q2', 'income_q3', 'income_q4')
    def _compute_income_total(self):
        for rec in self:
            rec.income_total = rec.income_q1 + rec.income_q2 + rec.income_q3 + rec.income_q4

    @api.depends('tax_q1', 'tax_q2', 'tax_q3', 'tax_q4')
    def _compute_tax_total(self):
        for rec in self:
            rec.tax_total = rec.tax_q1 + rec.tax_q2 + rec.tax_q3 + rec.tax_q4

    @api.depends('esv_base', 'esv_rate')
    def _compute_esv_amount(self):
        for rec in self:
            rec.esv_amount = rec.esv_base * rec.esv_rate / 100

    @api.onchange('income_q1', 'income_q2', 'income_q3', 'income_q4', 'tax_rate')
    def _onchange_income(self):
        """Auto-calculate tax from income."""
        rate = self.tax_rate / 100
        self.tax_q1 = self.income_q1 * rate
        self.tax_q2 = self.income_q2 * rate
        self.tax_q3 = self.income_q3 * rate
        self.tax_q4 = self.income_q4 * rate

    def _generate_xml_F0103309(self):
        """Generate XML for Single Tax Declaration (F0103309)."""
        self.ensure_one()

        # Determine reporting period
        period_type = self._get_period_type()
        period_month = self._get_period_month()

        # Build filename
        filename = f"{self.taxpayer_tin}_{self.year}_{period_month}_F0103309.xml"

        # Generate XML content
        xml = self._build_F0103309_xml(period_type, period_month)

        return xml, filename

    def _build_F0103309_xml(self, period_type, period_month):
        """Build the XML content for F0103309."""
        today = date.today()

        # Build activity codes XML
        activities_xml = ''
        for idx, activity in enumerate(self.activity_ids, 1):
            activities_xml += f'''    <T1RXXXXG1S ROWNUM="{idx}">{self._escape_xml(activity.code)}</T1RXXXXG1S>
    <T1RXXXXG2S ROWNUM="{idx}">{self._escape_xml(activity.name)}</T1RXXXXG2S>
'''

        # Get tax office codes
        tax_office_code = self.tax_office_id.code if self.tax_office_id else ''
        c_reg = tax_office_code[:2] if len(tax_office_code) >= 2 else ''
        c_raj = tax_office_code[2:4] if len(tax_office_code) >= 4 else ''
        tax_office_name = self.tax_office_id.name if self.tax_office_id else ''

        xml = f'''<?xml version="1.0" encoding="windows-1251"?>
<DECLAR xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="F0103309.xsd">
  <DECLARHEAD>
    <TIN>{self._escape_xml(self.taxpayer_tin)}</TIN>
    <C_DOC>F01</C_DOC>
    <C_DOC_SUB>033</C_DOC_SUB>
    <C_DOC_VER>09</C_DOC_VER>
    <C_DOC_TYPE>{self.declaration_type}</C_DOC_TYPE>
    <C_DOC_CNT>1</C_DOC_CNT>
    <C_REG>{c_reg}</C_REG>
    <C_RAJ>{c_raj}</C_RAJ>
    <PERIOD_MONTH>{period_month}</PERIOD_MONTH>
    <PERIOD_TYPE>{period_type}</PERIOD_TYPE>
    <PERIOD_YEAR>{self.year}</PERIOD_YEAR>
    <C_STI_ORIG>{tax_office_code}</C_STI_ORIG>
    <C_DOC_STAN>1</C_DOC_STAN>
    <D_FILL>{today.strftime('%d%m%Y')}</D_FILL>
  </DECLARHEAD>
  <DECLARBODY>
    <HFILL>{today.strftime('%d%m%Y')}</HFILL>
    <HZY>{self.year}</HZY>
    <HSTI>{self._escape_xml(tax_office_name)}</HSTI>
    <HNAME>{self._escape_xml(self.taxpayer_name)}</HNAME>
    <HLOC>{self._escape_xml(self.taxpayer_address or '')}</HLOC>
    <HEMAIL>{self._escape_xml(self.taxpayer_email or '')}</HEMAIL>
    <HTEL>{self._escape_xml(self.taxpayer_phone or '')}</HTEL>
    <HTIN>{self._escape_xml(self.taxpayer_tin)}</HTIN>
    <HNACTLG3>{1 if self.has_employees else 0}</HNACTLG3>
    <HNACTL>{self.employee_count}</HNACTL>
{activities_xml}    <R01G1>{self._format_amount(self.income_q1)}</R01G1>
    <R01G2>{self._format_amount(self.income_q2)}</R01G2>
    <R01G3>{self._format_amount(self.income_q3)}</R01G3>
    <R01G4>{self._format_amount(self.income_q4)}</R01G4>
    <R01G5>{self._format_amount(self.income_total)}</R01G5>
    <R02G1>{self._format_amount(self.tax_q1)}</R02G1>
    <R02G2>{self._format_amount(self.tax_q2)}</R02G2>
    <R02G3>{self._format_amount(self.tax_q3)}</R02G3>
    <R02G4>{self._format_amount(self.tax_q4)}</R02G4>
    <R02G5>{self._format_amount(self.tax_total)}</R02G5>
    <R03G1>{self._format_amount(self.esv_base)}</R03G1>
    <R03G2>{self._format_amount(self.esv_amount)}</R03G2>
    <HGROUP>{self.fop_group}</HGROUP>
    <HRATE>{self._format_amount(self.tax_rate)}</HRATE>
  </DECLARBODY>
</DECLAR>'''
        return xml

    def _format_amount(self, value):
        """Format amount for XML (2 decimal places, no thousands separator)."""
        if not value:
            return '0.00'
        return f'{value:.2f}'


class L10nUaTaxDocumentWizardActivity(models.TransientModel):
    """Activity codes (KVED) for tax declarations."""
    _name = 'l10n_ua.tax.document.wizard.activity'
    _description = 'Tax Document Wizard Activity Code'

    wizard_id = fields.Many2one(
        'l10n_ua.tax.document.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    kved_id = fields.Many2one(
        'l10n_ua.kved',
        string='KVED',
        required=True,
        domain=[('level', '=', 4)],  # Only class-level codes (e.g., 62.01)
    )
    code = fields.Char(
        string='Code',
        related='kved_id.code',
        store=True,
    )
    name = fields.Char(
        string='Name',
        related='kved_id.name',
        store=True,
    )
    is_primary = fields.Boolean(
        string='Primary',
        default=False,
    )
