from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from thunorweb.models import HTSDataset
from django.conf import settings
from django.contrib.admin.models import LogEntry, DELETION
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Remove datasets marked for deletion older than the retention time'

    def handle(self, *ars, **options):
        ct = ContentType.objects.get_for_model(HTSDataset)
        user_id = get_user_model().objects.get(email='AnonymousUser').pk

        for d in HTSDataset.objects.filter(deleted_date__lt=(
            timezone.now() - timedelta(days=settings.DATASET_RETENTION_DAYS)
        )):
            logger.info('Dataset {} deleted after retention time '
                        'elapsed'.format(d))
            LogEntry.objects.log_action(
                user_id=user_id,
                content_type_id=ct.id,
                object_id=d.id,
                object_repr=repr(d),
                action_flag=DELETION,
                change_message='Dataset deleted after retention time elapsed'
            )
            d.delete()
