from django.conf import settings
from django.core.management.base import BaseCommand
import os
import re
import time

DAYS_TO_SECONDS = 86400


class Command(BaseCommand):
    help = 'Clean up ephemeral download files'
    _filter = re.compile(r'^(xlsx(annot|assay))|h5dset')
    _max_age = settings.DOWNLOAD_EPHEMERAL_PURGE_DAYS * DAYS_TO_SECONDS

    def handle(self, *ars, **options):
        cutoff_time = time.time() - self._max_age
        hits = 0
        ignored = 0

        for f in os.listdir(settings.DOWNLOADS_ROOT):
            if self._filter.match(f):
                full_path = os.path.join(settings.DOWNLOADS_ROOT, f)
                if os.stat(full_path).st_mtime < cutoff_time:
                    os.remove(full_path)
                    hits += 1
                else:
                    ignored += 1

        self.stdout.write(self.style.SUCCESS('Temp files successfully '
                                             'cleaned (%d deleted, %d not '
                                             'old enough)' % (hits, ignored)))
