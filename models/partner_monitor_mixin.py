import logging, time
from psycopg2 import  DatabaseError
from odoo import models, api, _

_logger = logging.getLogger(__name__)

class PartnerMonitorMixin(models.AbstractModel):
    _name = 'azk.partner.monitor.mixin'
    _description = 'Azk Partner Monitor Mixin'

    @api.model
    def _post_cron_error(self, cron_name, error_message):
        params = self.env['ir.config_parameter'].sudo()
        user_id = params.get_param('azk_odoo_partner_monitor.error_recipient_user_id')
        if not user_id:
            _logger.error("The Partner Monitor error reception user is not configured.")
            return

        user = self.env['res.users'].browse(int(user_id))
        if not user.exists():
            _logger.error("User %s does not exist", user_id)
            return

        subject = _("Error in %s") % cron_name
        body = _("<b>Failed to start %s</b><br/><pre>%s</pre>") % (
            cron_name, error_message.replace("\n", "<br/>")
        )

        # We try twice at most in case of a serialization error.
        for attempt in range(2):
            try:
                user.message_post(body=body, subject=subject, subtype='mail.mt_note')
                return
            except DatabaseError as db_err:
                # Error code 40001 in PostgreSQL means Serialization Failure
                if 'could not serialize access' in str(db_err):
                    _logger.warning(
                        "%s/%s attempt to send chat message failed due to interference: %s",
                        attempt+1, 2, db_err
                    )
                    time.sleep(0.5)
                    continue
                _logger.error("Unexpected error posting chat message: %s", db_err)
                break
            except Exception as e:
                _logger.error("Unexpected failure in message_post: %s", e)
                break
        _logger.error("Sending error notification was unsuccessful after two attempts.")
