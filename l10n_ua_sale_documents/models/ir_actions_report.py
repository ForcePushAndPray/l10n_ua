from odoo import api, models
from odoo.tools.safe_eval import safe_eval, time


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    @api.model
    def _l10n_ua_eval_report_name(self, report, record):
        """File name of `report` for `record`, without extension (as mail templates do)."""
        if report.print_report_name:
            return safe_eval(report.print_report_name, {'object': record, 'time': time})
        return report.name
