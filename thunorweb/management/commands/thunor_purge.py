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
import json
import sys

logger = logging.getLogger(__name__)

MB_IN_BYTES = 1048576
VERBOSE_THRESHOLD = 2
INFO_THRESHOLD = 1
# One year, plus leeway for leap years/whatever
STATIC_FILE_MAX_AGE_DAYS = 370


class Command(BaseCommand):
    help = 'Remove old and expired files and datasets no longer needed by ' \
           'Thunor'

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.num_deleted = 0
        self.size_deleted = 0

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Don\'t actually delete anything',)

    def _delete_if_older_than(self, file, min_age_days, delete_callback=None,
                              **options):
        if not os.path.isfile(file):
            return
        date_cutoff = datetime.datetime.now() - datetime.timedelta(
            days=min_age_days)
        f_stat = os.stat(file)
        last_mod = datetime.datetime.utcfromtimestamp(f_stat.st_mtime)
        if last_mod > date_cutoff:
            return

        # Delete the file
        size_mb = f_stat.st_size / MB_IN_BYTES
        if int(options['verbosity']) >= VERBOSE_THRESHOLD:
            self.stdout.write(
                'Delete {} (last modified: {}, size: {:.2f}MiB)'.format(
                    os.path.basename(file),
                    last_mod.strftime('%Y-%m-%d %H:%M:%S'),
                    size_mb
                )
            )
        self.size_deleted += size_mb
        self.num_deleted += 1

        if not options['dry_run']:
            os.unlink(file)
            if delete_callback is not None:
                delete_callback()

    def _delete_old_bundles(self, *args, **options):
        stats_file = settings.WEBPACK_LOADER['DEFAULT']['STATS_FILE']
        with open(stats_file, 'r') as f:
            stats = json.load(f)

        if not stats['status'] == 'done':
            sys.stderr.write('Webpack bundle status is not "done"')
            sys.exit(1)

        files = [v['name'] for f in stats['chunks'].values() for v in f]
        files += os.path.basename(stats_file)

        # Clean up build files
        if int(options['verbosity']) > INFO_THRESHOLD:
            sys.stdout.write('Delete old webpack build files\n')
        for dir in settings.STATICFILES_DIRS:
            for file in os.listdir(dir):
                if file in files:
                    continue
                f = os.path.join(dir, file)
                self._delete_if_older_than(f, 0, **options)

        # Clean up static files
        if int(options['verbosity']) > INFO_THRESHOLD:
            sys.stdout.write('Delete old static files\n')
        for file in os.listdir(settings.STATIC_ROOT):
            f = os.path.join(settings.STATIC_ROOT, file)
            self._delete_if_older_than(f, STATIC_FILE_MAX_AGE_DAYS, **options)

    def handle(self, *args, **options):
        ct = ContentType.objects.get_for_model(HTSDataset)
        user_id = get_user_model().objects.get(email='AnonymousUser').pk

        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING('Dry run only (no delete commands will '
                                   'be executed)'))

        self._delete_old_bundles(*args, **options)

        # Delete datasets marked for deletion if retention time has expired
        if int(options['verbosity']) > INFO_THRESHOLD:
            sys.stdout.write('Delete expired datasets\n')
        for d in HTSDataset.objects.filter(deleted_date__lt=(
            timezone.now() - timedelta(days=settings.DATASET_RETENTION_DAYS)
        )):
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

        # Delete uploaded files not attached to a dataset, if old enough
        if int(options['verbosity']) > INFO_THRESHOLD:
            sys.stdout.write('Delete stale uploads\n')

        plate_files_dir = os.path.join(settings.MEDIA_ROOT, 'plate-files')

        plate_file_paths = set(pf.file.path for pf in PlateFile.objects.all())
        ct_platefile = ContentType.objects.get_for_model(PlateFile)

        for f_name in os.listdir(plate_files_dir):
            f = os.path.join(plate_files_dir, f_name)
            if f in plate_file_paths:
                continue

            def delete_callback():
                LogEntry.objects.log_action(
                    user_id=user_id,
                    content_type_id=ct_platefile.id,
                    object_id=None,
                    object_repr=f,
                    action_flag=DELETION,
                    change_message='Plate file deleted after retention '
                                   'time elapsed'
                )
            self._delete_if_older_than(f,
                                       settings.NON_DATASET_UPLOAD_RETENTION_DAYS,
                                       delete_callback=delete_callback,
                                       **options)

        self.stdout.write('Deleted {} files, total size {:.2f}MiB'.format(
            self.num_deleted, self.size_deleted))
