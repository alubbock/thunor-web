import argparse
import subprocess
import os
import sys
import shutil
import random
import time
from thunorweb import __version__ as thunorweb_version


class ThunorCtl(object):
    def __init__(self):
        self.cwd = os.path.abspath(os.path.dirname(__file__))

    def _set_args(self, args):
        print('Thunorctl: Thunor Web {}'.format(thunorweb_version))
        self.args = args
        if args.thunorhome:
            self.thunorhome = args.thunorhome
        else:
            try:
                self.thunorhome = os.environ['THUNORHOME']
            except KeyError:
                if 'use_docker_machine' in self.args and \
                        self.args.use_docker_machine:
                    raise ValueError(
                        'Cannot use Docker Machine without specifying value '
                        'for THUNORHOME. Specify the *remote* location to '
                        'install Thunor using --thunorhome argument or the '
                        'THUNORHOME environment variable.')

                self.thunorhome = self.cwd

        if self.args.dry_run:
            print('Thunorctl: DRY RUN (no commands will be executed)')

        print('Thunorctl: THUNORHOME set to {}'.format(self.thunorhome))

    def _run_cmd(self, cmd, exit_on_error=True):
        print('Thunorctl command: ' + (' '.join(cmd)))
        if self.args.dry_run:
            return 0
        env = os.environ.copy()
        env['THUNORHOME'] = self.thunorhome
        result = subprocess.call(cmd, cwd=self.cwd, env=env)
        if exit_on_error and result != 0:
            print('Thunorctl: Process exited with status {},'
                  'aborting...'.format(result))
            sys.exit(result)
        return result

    def _copy(self, fromfile, tofile):
        fromfile = os.path.join(self.cwd, fromfile)
        tofile = os.path.join(self.cwd, tofile)
        print('Thunorctl copy: ' + fromfile + ' to ' + tofile)
        if self.args.dry_run:
            return
        if os.path.exists(tofile):
            print('Thunorctl: Destination file exists, aborting...')
            sys.exit(1)
        shutil.copy2(fromfile, tofile)

    def _mkdir(self, dirname):
        dirname = os.path.join(self.cwd, dirname)
        print('Thunorctl mkdir: ' + dirname)
        if self.args.dry_run:
            return
        os.makedirs(dirname)

    def _rmdir(self, dirname):
        dirname = os.path.join(self.cwd, dirname)
        print('Thunorctl delete: ' + dirname)
        if self.args.dry_run:
            return
        shutil.rmtree(dirname)

    def _check_docker_compose(self):
        try:
            self._run_cmd(['docker-compose', '--version'])
        except FileNotFoundError:
            msg = '\ndocker-compose not found. '
            if sys.platform == 'darwin':
                msg += 'Download from ' \
                       'https://download.docker.com/mac/stable/Docker.dmg'
            elif sys.platform.startswith('win'):
                msg += 'Download from ' \
                       'https://download.docker.com/win/stable/' \
                       'Docker%20for%20Windows%20Installer.exe'
            else:
                msg += 'See https://docs.docker.com/compose/install/'
            print(msg)
            sys.exit(1)

    @staticmethod
    def _random_string(length=50):
        """ Generate a random key for Django """
        SECURE_KEY_CHARS = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
        rand = random.SystemRandom()
        return ''.join(rand.choice(SECURE_KEY_CHARS) for _ in range(length))

    @staticmethod
    def _replace_in_file(filename, from_str, to_str):
        """ In-place replacement of string in file, for config generation """

        with open(filename, 'r') as file:
            filedata = file.read()

        filedata = filedata.replace(from_str, to_str)

        with open(filename, 'w') as file:
            file.write(filedata)

    def _generate_random_key(self, filename, keyname):
        """ Replace a config file placeholder with a random key """
        print('Thunorctl keygen: {} in {}'.format(keyname, filename))
        key = self._random_string()
        if not self.args.dry_run:
            self._replace_in_file(os.path.join(self.cwd, filename),
                                  keyname,
                                  key)

    def migrate(self):
        if self.args.dev:
            return self._run_cmd(['python', 'manage.py', 'migrate'])
        else:
            return self._run_cmd(['docker-compose', 'run', '--rm', 'app',
                                  'python', 'manage.py', 'migrate'])

    def _build_webpack(self):
        return self._run_cmd(['docker', 'build', '-t', 'thunorweb_webpack',
                              'thunorweb/webpack'])

    @property
    def _volume_webpack_bundles(self):
        return os.path.join(self.thunorhome, '_state/webpack-bundles') + \
                            ':/thunor/_state/webpack-bundles'

    @property
    def _volume_webpack_static(self):
        return os.path.join(self.thunorhome, '_state/thunor-static-build') + \
                            ':/thunor/_state/thunor-static'

    @property
    def _volume_thunor_files(self):
        return os.path.join(self.thunorhome, '_state/thunor-files') + \
                            ':/thunor/_state/thunor-files'

    def generate_static(self):
        self._build_webpack()
        cmd = ['docker', 'run', '--rm']
        if self.args.dev:
            cmd += ['-e', 'DJANGO_DEBUG=True']
        cmd += ['-v', self._volume_webpack_bundles, 'thunorweb_webpack']
        return self._run_cmd(cmd)

    def _build_base_image(self):
        return self._run_cmd(['docker', 'build', '-t', 'thunorweb_base',
                              '--build-arg',
                              'THUNORWEB_VERSION={}'.format(
                                  thunorweb_version),
                              '-f',
                              os.path.join(self.cwd, 'Dockerfile.base'),
                              self.cwd])

    def collect_static(self):
        cmd = ['python', 'manage.py', 'collectstatic', '--no-input']

        if not self.args.dev:
            self._build_base_image()
            self._mkdir('_state/thunor-static-build')
            self._copy('config-examples/502.html',
                       '_state/thunor-static-build/502.html')
            cmd = ['docker',
                   'run',
                   '--rm',
                   '-v', self._volume_webpack_bundles,
                   '-v', self._volume_webpack_static,
                   '-e', 'DJANGO_DEBUG=False',
                   '-e', 'DJANGO_SECRET_KEY=not_needed',
                   '-e', 'DJANGO_EMAIL_HOST=',
                   '-e', 'DJANGO_EMAIL_PORT=',
                   '-e', 'DJANGO_EMAIL_USER=',
                   '-e', 'DJANGO_EMAIL_PASSWORD=',
                   '-e', 'POSTGRES_PASSWORD=',
                   'thunorweb_base'] + cmd

        return self._run_cmd(cmd)

    def make_static(self):
        self.generate_static()
        self.collect_static()

    def thunorweb_build(self):
        if self.args.dev:
            raise ValueError('Cannot build Docker container in dev mode')

        self.make_static()
        self._run_cmd(['docker',
                       'build',
                       '-t', 'alubbock/thunorweb:dev',
                       self.cwd])
        if 'cleanup' in self.args and self.args.cleanup:
            self._rmdir('_state/thunor-static-build')

    def thunorweb_upgrade(self):
        self.migrate()
        if self.args.dev:
            self.make_static()
        else:
            self.thunorweb_build()

    def thunor_purge(self):
        cmd = ['python', 'manage.py', 'thunor_purge']
        if self.args.verbosity > 0:
            cmd += ['--verbosity={}'.format(self.args.verbosity)]
        if self.args.dry_run:
            cmd += ['--dry-run']

        if not self.args.dev:
            cmd = ['docker-compose',
                   'run',
                   '--rm',
                   # '-v', self._volume_webpack_bundles,
                   # '-v', self._volume_webpack_static,
                   '-v', self._volume_thunor_files,
                   'app'] + cmd

        return self._run_cmd(cmd)

    def _certbot_cmd(self):
        return ['docker-compose', '-f',
                os.path.join(self.cwd, 'docker-compose.certbot.yml'),
                'run', '--rm', 'certbot']

    def _generate_dhparams(self):
        # Does dhparams.pem file already exist?
        file_exists = self._run_cmd(
            self._certbot_cmd() +
            ['test', '-f', '/etc/letsencrypt/dhparams.pem'],
            exit_on_error=False
        ) == 0
        if file_exists:
            print('Thunorctl: dhparams.pem file exists, skipping...')
            return

        self._run_cmd(
            self._certbot_cmd() + ['openssl', 'dhparam', '-out',
                                   '/etc/letsencrypt/dhparams.pem', '2048']
        )

    def _generate_certificate(self):
        cmd = self._certbot_cmd() + [
            'certbot', 'certonly', '--webroot', '--webroot-path',
            '/thunor-static'] + self.args.letsencrypt_args
        return self._run_cmd(cmd)

    def generate_certificates(self):
        self._generate_dhparams()
        self._generate_certificate()

    def renew_certificates(self):
        self._run_cmd(self._certbot_cmd() +
                      ['certbot', 'renew', '--non-interactive'])

        self._run_cmd(['docker-compose', 'exec', 'nginx', 'nginx',
                       '-s', 'reload'])

    def generate_skeleton(self):
        if self.args.dev:
            self._copy('config-examples/thunor-dev.env', 'thunor-dev.env')
            self._generate_random_key('thunor-dev.env', '{{DJANGO_SECRET_KEY}}')
            self._generate_random_key('thunor-dev.env', '{{POSTGRES_PASSWORD}}')
            self._copy('config-examples/docker-compose.postgresonly.yml',
                       'docker-compose.yml')
            if not self.args.dry_run:
                self._replace_in_file(
                    os.path.join(self.cwd, 'docker-compose.yml'),
                    '- thunor-db.env',
                    '- thunor-dev.env'
                )
        else:
            self._copy('config-examples/docker-compose.complete.yml',
                       'docker-compose.yml')
            self._copy('config-examples/thunor-db.env', 'thunor-db.env')
            self._generate_random_key('thunor-db.env', '{{POSTGRES_PASSWORD}}')
            self._copy('config-examples/thunor-app.env',
                       'thunor-app.env')
            self._generate_random_key('thunor-app.env', '{{DJANGO_SECRET_KEY}}')
            self._mkdir('_state/nginx-config')
            self._copy('config-examples/nginx.base.conf',
                       '_state/nginx-config/nginx.base.conf')
            self._copy('config-examples/nginx.site-basic.conf',
                       '_state/nginx-config/nginx.site.conf')

        self._mkdir('_state/postgres-data')

    def quickstart(self):
        if os.path.exists(os.path.join(self.cwd, '_state')):
            raise ValueError('_state directory already exists. Is Thunor '
                             'already installed?')
        docker_machine = False
        docker_ip = None
        if 'DOCKER_MACHINE_NAME' in os.environ:
            if self.args.dev:
                raise ValueError('Cannot use --dev when Docker Machine is '
                                 'active')
            if not self.args.use_docker_machine:
                raise ValueError('Docker Machine is active but '
                                 '--use-docker-machine not set. '
                                 'Either set --use-docker-machine or unset '
                                 'Docker Machine environment variables '
                                 '(docker-machine env --unset).')
            docker_machine = os.environ['DOCKER_MACHINE_NAME']

            docker_ip = subprocess.check_output(['docker-machine', 'ip',
                                                 docker_machine]).strip().\
                decode('utf8')
            print('Thunorctl: Docker Machine IP is ' + docker_ip)

            self._run_cmd(['docker-machine', 'ssh', docker_machine,
                           'mkdir', '"' + self.thunorhome + '"'])
        elif self.args.use_docker_machine:
            raise ValueError('--use-docker-machine set, but Docker Machine is '
                             'not active. Have you activated the machine\'s '
                             'environment?')

        self._check_docker_compose()
        if self.args.dev:
            if os.environ.get('DJANGO_DEBUG', 'False').lower() != 'true':
                raise ValueError(
                    'Please make sure that the DJANGO_DEBUG environment '
                    'variable is set to True before installing in dev mode')
            self._run_cmd(['pip', 'install', '-r', 'requirements-dev.txt'])
        self.generate_skeleton()
        if docker_machine:
            if docker_ip:
                print('Thunorctl: set DJANGO_HOSTNAME in thunor-app.env '
                      'to {}'.format(docker_ip))
                if not self.args.dry_run:
                    self._replace_in_file(
                        os.path.join(self.cwd, 'thunor-app.env'),
                        'DJANGO_HOSTNAME=localhost',
                        'DJANGO_HOSTNAME=' + docker_ip
                    )
            self._run_cmd(['docker-machine', 'scp', '-r', '_state',
                           '{}:"{}"'.format(
                               docker_machine, self.thunorhome)])

        # Build container, if not running in dev mode
        if self.args.dev:
            self.make_static()
        else:
            self.thunorweb_build()

        self._run_cmd(['docker-compose', 'up', '-d', 'postgres'])

        if not self.args.dry_run:
            # Wait for postgres to start
            pg_retry = 0
            pg_max_retry = 40
            pg_retry_delay = 5
            while self._run_cmd(
                    ['docker-compose', 'exec', 'postgres', 'pg_isready'],
                    exit_on_error=False) != 0 and pg_retry < pg_max_retry:
                print('Postgres not yet ready, sleeping {} seconds...'.format(
                    pg_retry_delay
                ))
                pg_retry += 1
                time.sleep(pg_retry_delay)

            if pg_retry == pg_max_retry:
                print('Postgres not responding, exiting...')
                sys.exit(1)

        self.migrate()

        if self.args.dev:
            self._run_cmd(['python', 'manage.py', 'createcachetable'])

        print('\nQuickstart complete! Next steps:')

        if not self.args.dev:
            print(
                '* You\'ll need to set up a working email server '
                'configuration \n'
                '  OR set DJANGO_DEBUG=False in thunor-app.env (the latter \n'
                '  should not be set in production!) before you can log in.\n'
                '* You may wish to set the value of DJANGO_HOSTNAME to a\n'
                '  different domain name in thunor-app.env. The server can\n'
                '  only be accessed by the specified hostname.')
            if docker_machine and os.environ.get('THUNORHOME', '') != \
                    self.thunorhome:
                print('* Set THUNORHOME in your environment to ' +
                      self.thunorhome)
            print('* Start the server with "docker-compose up -d"')
        print('* Create an admin account with '
              '"python thunorctl.py createsuperuser"')
        if self.args.dev:
            print('* Run "python manage.py runserver" to start the development '
                  'server')

    def createsuperuser(self):
        if self.args.dev:
            self._run_cmd(['python', 'manage.py', 'createsuperuser'])
        else:
            self._run_cmd(['docker-compose', 'exec', 'app',
                          'python', 'manage.py', 'createsuperuser'])

    def run_tests(self):
        if self.args.dev:
            self._run_cmd(['python', 'manage.py', 'test'])
        else:
            self._run_cmd(['docker-compose', 'run', '--rm', '-e',
                           'THUNORHOME=/thunor', 'app',
                           'python', 'manage.py', 'test'])

    def _parser(self):
        parser = argparse.ArgumentParser(prog='thunorctl.py')
        parser.add_argument('--dev', action='store_true',
                            help='Developer mode (app runs outside of Docker)')
        parser.add_argument('--dry-run', action='store_true', default=False,
                            help='Dry run (don\'t execute any commands, '
                                 'just show them)')
        parser.add_argument(
            '--thunorhome', help=
            'Path to Thunor Web on the target machine, or use environment '
            'variable THUNORHOME. Not needed for local installations.')
        subparsers = parser.add_subparsers()

        parser_migrate = subparsers.add_parser(
            'migrate', help='Initialise or migrate the database')
        parser_migrate.set_defaults(func=self.migrate)

        parser_make_static = subparsers.add_parser(
            'makestatic', help='Generate static files and collect them in '
                               'Django. Equivalent to generatestatic and '
                               'collectstatic called sequentially.'
        )
        parser_make_static.set_defaults(func=self.make_static)

        parser_generate_static = subparsers.add_parser(
            'generatestatic', help='Generate static files'
        )
        parser_generate_static.set_defaults(func=self.generate_static)

        parser_collect_static = subparsers.add_parser(
            'collectstatic', help='Collect static files in Django'
        )
        parser_collect_static.set_defaults(func=self.collect_static)

        parser_generate_certs = subparsers.add_parser(
            'generatecerts', help='Generate TLS certificates. Additional '
                                  'arguments are passed onto letsencrypt.'
        )
        parser_generate_certs.add_argument('letsencrypt_args',
                                           nargs=argparse.REMAINDER)
        parser_generate_certs.set_defaults(func=self.generate_certificates)

        parser_thunor_purge = subparsers.add_parser(
            'purge', help='Purge Thunor Web of temporary files to reclaim disk '
                          'space.'
        )
        parser_thunor_purge.add_argument('--dry-run', action='store_true',
                                         default=False)
        parser_thunor_purge.add_argument('--verbosity', type=int,
                                         default=0)
        parser_thunor_purge.set_defaults(func=self.thunor_purge)

        parser_upgrade = subparsers.add_parser(
            'upgrade', help='Upgrade Thunor Web. Equivalent to makestatic, '
                            'migrate, and build called '
                            'sequentially.'
        )
        parser_upgrade.set_defaults(func=self.thunorweb_upgrade)

        parser_build = subparsers.add_parser(
            'build', help='Build Thunor Web Docker container'
        )
        parser_build.add_argument(
            '--cleanup', action='store_true', default=False,
            help='Cleanup intermediate build files'
        )
        parser_build.set_defaults(func=self.thunorweb_build)

        parser_renew_certs = subparsers.add_parser(
            'renewcerts', help='Renew TLS certificates'
        )
        parser_renew_certs.set_defaults(func=self.renew_certificates)

        parser_skeleton = subparsers.add_parser(
            'skeleton', help='Create quickstart skeleton configuration files'
        )
        parser_skeleton.set_defaults(func=self.generate_skeleton)

        parser_quickstart = subparsers.add_parser(
            'quickstart', help='Generate example config and start Thunor Web'
        )
        parser_quickstart.add_argument(
            '--use-docker-machine', action='store_true', default=False,
            help='Use Docker Machine. Be sure to set installation location on '
                 '*remote* machine using --thunorhome or THUNORHOME '
                 'environment variable.'
        )
        parser_quickstart.set_defaults(func=self.quickstart)

        parser_superuser = subparsers.add_parser(
            'createsuperuser', help='Create a Thunor Web admin account'
        )
        parser_superuser.set_defaults(func=self.createsuperuser)

        parser_test = subparsers.add_parser(
            'test', help='Run Thunor Web test suite'
        )
        parser_test.set_defaults(func=self.run_tests)

        parser.add_argument('--version', action='version',
                            version=thunorweb_version)

        return parser


if __name__ == '__main__':
    thunorctl = ThunorCtl()
    parser = thunorctl._parser()
    parser_args = parser.parse_args()
    thunorctl._set_args(parser_args)
    if hasattr(parser_args, 'func'):
        parser_args.func()
