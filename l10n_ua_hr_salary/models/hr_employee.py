from dateutil.relativedelta import relativedelta

from odoo import models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def _l10n_ua_month_norm(self, company, on_date, version=None):
        """The working time norm of the month of `on_date`: (days, hours).

        The norm of the month itself: an absence, a hire in the middle of the
        month, a part-time rate or a shift schedule does not shorten it. Each
        day is read the way the timesheet generator reads it: from the
        production calendar when the company keeps one for the year and has
        the day in it, otherwise Monday to Friday. The calendar is optional on
        purpose — under martial law public holidays are working days, and an
        empty calendar is a valid setup, not a missing one.

        The hours of a day are those of a full-time day of the company's
        working schedule, 8 when it has none — or of the employee's schedule
        on a reduced working time, which is their whole norm. The version of
        each day is the one in force on it, `version` when there is none.

        The payslip and the advance read the norm here, so that both pay an
        hour at the same rate.
        """
        self.ensure_one()
        version = version if version is not None else self.env['hr.version']
        month_start = on_date.replace(day=1)
        working = company._l10n_ua_working_dates(
            month_start, month_start + relativedelta(months=1, days=-1))
        return len(working), sum(
            (self._l10n_ua_version_on(day) or version)._l10n_ua_norm_hours(hours)
            for day, hours in working.items())
