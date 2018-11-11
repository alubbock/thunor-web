from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from thunorweb.models import HTSDataset, PlateFile
from django.conf import settings
from django.contrib.admin.models import LogEntry, DELETION
import logging
import os
import datetime

logger = logging.getLogger(__name__)

MB_IN_BYTES = 1048576
VERBOSE_THRESHOLD = 2


class Command(BaseCommand):
    help = 'Remove datasets marked for deletion older than the retention time' \
           ', and old file uploads not attached to a dataset'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Don\'t actually delete anything',)

    def handle(self, *args, **options):
        ct = ContentType.objects.get_for_model(HTSDataset)
        user_id = get_user_model().objects.get(email='AnonymousUser').pk

        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING('Dry run only (no delete commands will '
                                   'be executed)'))

        n_removed = 0

        # Delete datasets marked for deletion if retention time has expired
        for d in HTSDataset.objects.filter(deleted_date__lt=(
            timezone.now() - timedelta(days=settings.DATASET_RETENTION_DAYS)
        )):
            n_removed += 1
            if int(options['verbosity']) >= VERBOSE_THRESHOLD:
                self.stdout.write('Remove dataset {} (deleted on {})'.format(
                    d, d.modified_date))
            if options['dry_run']:
                continue
            LogEntry.objects.log_action(
                user_id=user_id,
                content_type_id=ct.id,
                object_id=d.id,
                object_repr=repr(d),
                action_flag=DELETION,
                change_message='Dataset removed after retention time elapsed'
            )
            d.delete()

        # Delete uploaded files not attached to a dataset if old enough
        date_cutoff = datetime.datetime.now() - datetime.timedelta(
            days=settings.NON_DATASET_UPLOAD_RETENTION_DAYS)
        plate_files_dir = os.path.join(settings.MEDIA_ROOT, 'plate-files')

        plate_file_paths = set(pf.file.path for pf in PlateFile.objects.all())
        ct_platefile = ContentType.objects.get_for_model(PlateFile)

        total_size_mb = 0.0
        n_deleted = 0
        for f_name in os.listdir(plate_files_dir):
            f = os.path.join(plate_files_dir, f_name)
            if f in plate_file_paths:
                continue
            f_stat = os.stat(f)
            last_mod = datetime.datetime.utcfromtimestamp(f_stat.st_mtime)

            if last_mod < date_cutoff and os.path.isfile(f):
                # os.remove(os.path.join(path, f))
                size_mb = f_stat.st_size / MB_IN_BYTES
                total_size_mb += size_mb
                n_deleted += 1
                if int(options['verbosity']) >= VERBOSE_THRESHOLD:
                    self.stdout.write(
                        'Delete {} (last modified: {}, size: {:.2f}MiB)'.format(
                            f_name,
                            last_mod.strftime('%Y-%m-%d %H:%M:%S'),
                            size_mb
                        )
                    )
                if not options['dry_run']:
                    LogEntry.objects.log_action(
                        user_id=user_id,
                        content_type_id=ct_platefile.id,
                        object_id=None,
                        object_repr=f,
                        action_flag=DELETION,
                        change_message='Plate file deleted after retention '
                                       'time elapsed'
                    )
                    os.unlink(f)

        self.stdout.write('Removed {} expired datasets'.format(n_removed))

        self.stdout.write('Deleted {} files, total size {:.2f}MiB'.format(
            n_deleted, total_size_mb))
