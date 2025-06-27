import logging, time
from psycopg2 import  DatabaseError
from odoo import models, api, _

_logger = logging.getLogger(__name__)

class PartnerMonitorMixin(models.AbstractModel):
    _name = 'azk.partner.monitor.mixin'

    @api.model
    def _post_cron_error(self, cron_name, error_message):
        params = self.env['ir.config_parameter'].sudo()
        user_id = params.get_param('azk_odoo_partner_monitor.error_recipient_user_id')
        if not user_id:
            _logger.error("لم يتم تكوين مستخدم استقبال أخطاء Partner Monitor")
            return

        user = self.env['res.users'].browse(int(user_id))
        if not user.exists():
            _logger.error("المستخدم %s غير موجود", user_id)
            return

        subject = _("خطأ في %s") % cron_name
        body = _("<b>فشِل تشغيل %s</b><br/><pre>%s</pre>") % (
            cron_name, error_message.replace("\n", "<br/>")
        )

        # نحاول مرتين على الأكثر في حال خطأ SERIALIZATION
        for attempt in range(2):
            try:
                user.message_post(body=body, subject=subject, subtype='mail.mt_note')
                return
            except DatabaseError as db_err:
                # كود الخطأ 40001 في PostgreSQL يعني Serialization Failure
                if 'could not serialize access' in str(db_err):
                    _logger.warning(
                        "محاولة %s/%s لإرسال رسالة الدردشة فشلت بسبب تداخل: %s",
                        attempt+1, 2, db_err
                    )
                    time.sleep(0.5)  # انتظر نصف ثانية ثم أعد المحاولة
                    continue
                # خطأ آخر: أُعيد طرحه
                _logger.error("خطأ غير متوقع في نشر رسالة الدردشة: %s", db_err)
                break
            except Exception as e:
                _logger.error("فشل غير متوقع في message_post: %s", e)
                break
        _logger.error("لم ينجح إرسال إشعار الخطأ بعد محاولتين.")
