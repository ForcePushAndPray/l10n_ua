"""Install/upgrade hooks for l10n_ua_account_base."""

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Populate `group_has_ua_company` for existing users on (re)install."""
    env['res.users'].with_context(active_test=False).search(
        [('share', '=', False)])._l10n_ua_recompute_has_ua_company()
    _logger.info("l10n_ua_account_base: group_has_ua_company populated")
