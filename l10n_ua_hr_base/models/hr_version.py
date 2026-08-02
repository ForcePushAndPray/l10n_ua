from odoo import models, api

from .hr_employee import REGISTRATION_ADDRESS_MAP


class HrVersion(models.Model):
    _inherit = 'hr.version'

    @api.constrains('country_id')
    def _check_ua_military_citizenship(self):
        """Mirror of the employee-side check, from where nationality lives.

        `country_id` is stored on the version, so setting a foreign
        nationality on an employee card writes hr.version and never triggers
        an hr.employee constraint. Only the current version counts — the
        employee's own `country_id` reads from it.
        """
        for version in self:
            employee = version.employee_id
            if employee and employee.current_version_id == version:
                employee._assert_military_matches_citizenship()

    def _sync_ua_registration_address(self):
        """Push the private address of the current version onto the employee.

        private_* physically lives here, not on hr.employee, so signing a new
        contract, changing a status or editing a version straight from the
        version list never goes through hr.employee.write(). Without this hook
        the registration block silently drifts away from the address it is
        supposed to mirror.

        Only the version that is currently authoritative counts: editing a past
        or future version must not rewrite today's registration address.
        """
        current = self.filtered(
            lambda version: version.employee_id
            and version.employee_id.current_version_id == version)
        current.employee_id._sync_registration_address_from_private()

    @api.model_create_multi
    def create(self, vals_list):
        versions = super().create(vals_list)
        versions._sync_ua_registration_address()
        return versions

    def write(self, vals):
        res = super().write(vals)
        if not REGISTRATION_ADDRESS_MAP.keys().isdisjoint(vals):
            self._sync_ua_registration_address()
        return res
