import argparse
import subprocess
import os
import sys
import shutil
import random
import time
import logging


class ThunorCmdHelper(object):
    def __init__(self):
        self._log = logging.getLogger(self.__class__.__name__)
        self._log.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        fmt = logging.Formatter(
            '%(name)s [%(levelname)s] %(message)s'
        )
        ch.setFormatter(fmt)
        self._log.addHandler(ch)

        self.cwd = os.path.abspath(os.path.dirname(__file__))

    def _set_args(self, args):
        self.args = args

        if self.args.dry_run:
            self._log.warning('DRY RUN (no commands will be executed)')

    def _run_cmd(self, cmd, exit_on_error=True):
        self._log.info('Command: ' + (' '.join(cmd)))
        if self.args.dry_run:
            return 0
        result = subprocess.call(cmd, cwd=self.cwd)
        if exit_on_error and result != 0:
            self._log.error(
                'Process exited with status {},'
                'aborting...'.format(result)
            )
            sys.exit(result)
        return result

    def _copy(self, fromfile, tofile, overwrite=False):
        fromfile = os.path.join(self.cwd, fromfile)
        if not tofile.startswith('/'):
            tofile = os.path.join(self.cwd, tofile)
        self._log.info('Copy: ' + fromfile + ' to ' + tofile)
        if self.args.dry_run:
            return
        if not overwrite and os.path.exists(tofile):
            self._log.error('Destination file exists, aborting...')
            sys.exit(1)
        shutil.copy2(fromfile, tofile)

    def _mkdir(self, dirname):
        if not dirname.startswith('/'):
            dirname = os.path.join(self.cwd, dirname)
        self._log.info('Mkdir: ' + dirname)
        if self.args.dry_run:
            return
        os.makedirs(dirname)

    def _rmdir(self, dirname):
        dirname = os.path.join(self.cwd, dirname)
        self._log.info('Delete: ' + dirname)
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
            self._log.error(msg)
            sys.exit(1)

    @staticmethod
    def _random_string(length=50):
        """ Generate a random key for Django """
        SECURE_KEY_CHARS = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
        rand = random.SystemRandom()
        return ''.join(rand.choice(SECURE_KEY_CHARS) for _ in range(length))

    def _replace_in_file(self, filename, from_str, to_str, log=True):
        """ In-place replacement of string in file, for config generation """

        if log:
            self._log.debug('Replace: "{}" with "{}" in {}'.format(
                from_str, to_str, filename))

        if self.args.dry_run:
            return

        with open(filename, 'r') as file:
            filedata = file.read()

        filedata = filedata.replace(from_str, to_str)

        with open(filename, 'w') as file:
            file.write(filedata)

    def _generate_random_key(self, filename, keyname):
        """ Replace a config file placeholder with a random key """
        self._log.info('Keygen: {} in {}'.format(keyname, filename))
        key = self._random_string()

        self._replace_in_file(os.path.join(self.cwd, filename),
                              keyname, key, log=False)

    def _prepare_deployment_common(self, subdir=''):
        self._copy('config-examples/thunor-db.env',
                   os.path.join(subdir, 'thunor-db.env'))
        self._generate_random_key(
            os.path.join(subdir, 'thunor-db.env'),
            '{{POSTGRES_PASSWORD}}')
        self._copy('config-examples/thunor-app.env',
                   os.path.join(subdir, 'thunor-app.env'))
        self._generate_random_key(os.path.join(subdir, 'thunor-app.env'),
                                  '{{DJANGO_SECRET_KEY}}')
        self._mkdir(os.path.join(subdir, '_state/nginx-config'))
        self._copy('config-examples/nginx.base.conf',
                   os.path.join(subdir, '_state/nginx-config/nginx.base.conf'))

    def _wait_postgres(self, compose_file='docker-compose.yml'):
        # Wait for postgres to start
        pg_retry = 0
        pg_max_retry = 40
        pg_retry_delay = 5
        while self._run_cmd(
                ['docker-compose', '-f', compose_file,
                 'exec', 'postgres', 'pg_isready'],
                exit_on_error=False) != 0 and pg_retry < pg_max_retry:
            print('Postgres not yet ready, sleeping {} seconds...'.format(
                pg_retry_delay
            ))
            pg_retry += 1
            time.sleep(pg_retry_delay)

        if pg_retry == pg_max_retry:
            print('Postgres not responding, exiting...')
            sys.exit(1)


class ThunorCtl(ThunorCmdHelper):
    def migrate(self):
        if self.args.dev:
            return self._run_cmd(['python', 'manage.py', 'migrate'])
        else:
            return self._run_cmd(['docker-compose', 'run', '--rm', 'app',
                                  'python', 'manage.py', 'migrate'])

    def thunorweb_upgrade(self):
        if self.args.dev:
            from thunorbld import ThunorBld
            bld = ThunorBld()
            bld._set_args(self.args)
            bld.make_static()
        else:
            self._run_cmd(['docker-compose', 'pull', 'app'])
            self._run_cmd(['docker-compose', 'down', '-v'])
            self._run_cmd(['docker-compose', 'up', '-d'])
        self.migrate()

    def thunorweb_purge(self):
        cmd = ['python', 'manage.py', 'thunor_purge']
        if self.args.verbosity > 0:
            cmd += ['--verbosity={}'.format(self.args.verbosity)]
        if self.args.dry_run:
            cmd += ['--dry-run']

        if not self.args.dev:
            cmd = ['docker-compose',
                   'run',
                   '--rm',
                   'app'] + cmd

        return self._run_cmd(cmd)

    @property
    def _certbot_cmd(self):
        return ['docker-compose', '-f',
                os.path.join(self.cwd, 'docker-compose.certbot.yml'),
                'run', '--rm', 'certbot']

    def _generate_dhparams(self):
        # Does dhparams.pem file already exist?
        file_exists = self._run_cmd(
            self._certbot_cmd +
            ['test', '-f', '/etc/letsencrypt/dhparams.pem'],
            exit_on_error=False
        ) == 0
        if file_exists:
            print('Thunorctl: dhparams.pem file exists, skipping...')
            return

        self._run_cmd(
            self._certbot_cmd + ['openssl', 'dhparam', '-out',
                                 '/etc/letsencrypt/dhparams.pem', '2048']
        )

    def _generate_certificate(self):
        cmd = self._certbot_cmd + \
            ['certbot', '--nginx'] + self.args.letsencrypt_args
        return self._run_cmd(cmd)

    def generate_certificates(self):
        self._generate_dhparams()
        self._generate_certificate()

    def renew_certificates(self):
        self._run_cmd(self._certbot_cmd +
                      ['certbot', 'renew', '--non-interactive'])

        self._run_cmd(['docker-compose', 'exec', 'nginx', 'nginx',
                       '-s', 'reload'])

    def deploy(self):
        if self.args.dev:
            raise ValueError('Deployment not available/needed in dev mode')

        if os.path.exists(os.path.join(self.cwd, '_state')):
            raise ValueError('_state directory already exists. Is Thunor Web '
                             'already installed?')

        self._check_docker_compose()

        self._prepare_deployment_common()
        self._copy('config-examples/docker-compose.complete.yml',
                   'docker-compose.yml')

        self._copy('config-examples/nginx.site-basic.conf',
                   '_state/nginx-config/nginx.site.conf')

        self._mkdir('_state/postgres-data')

        docker_machine = False
        docker_ip = None
        if 'DOCKER_MACHINE_NAME' in os.environ:
            if not self.args.thunorhome:
                raise ValueError('Docker Machine is active but '
                                 '--thunorhome not set. '
                                 'Either set --thunorhome option, or unset '
                                 'Docker Machine environment variables '
                                 '(docker-machine env --unset).')
            docker_machine = os.environ['DOCKER_MACHINE_NAME']

            docker_ip = subprocess.check_output(['docker-machine', 'ip',
                                                 docker_machine]).strip().\
                decode('utf8')
            self._log.info('Docker Machine IP is ' + docker_ip)

            self._run_cmd(['docker-machine', 'ssh', docker_machine,
                           'mkdir', '"' + self.args.thunorhome + '"'])
        elif self.args.thunorhome:
            raise ValueError('--thunorhome set, but Docker Machine is '
                             'not active. Have you activated the machine\'s '
                             'environment? If you\'re attempting a local '
                             'installation, this option is not needed.')

        if not self.args.hostname:
            if docker_ip:
                self.args.hostname = docker_ip
            else:
                self.args.hostname = 'localhost'

            new_hostname = input('Enter a hostname (default: {}) : '.format(
                self.args.hostname
            ))
            if new_hostname.strip():
                self.args.hostname = new_hostname

        self._log.info('Set DJANGO_HOSTNAME in thunor-app.env to {}'.format(
            self.args.hostname))

        self._replace_in_file(
            os.path.join(self.cwd, 'thunor-app.env'),
            'DJANGO_HOSTNAME=localhost',
            'DJANGO_HOSTNAME=' + self.args.hostname
        )

        if docker_machine:
            self._run_cmd(['docker-machine', 'scp', '-r', '_state',
                           '{}:"{}"'.format(
                               docker_machine, self.args.thunorhome)])

        self._run_cmd(['docker-compose', 'up', '-d'])

        if not self.args.dry_run:
            self._wait_postgres()

        self.migrate()

        print('\nDeploy complete! Next steps:')

        print('* Create an admin account with '
              '"python thunorctl.py createsuperuser"')

    def createsuperuser(self):
        if self.args.dev:
            self._run_cmd(['python', 'manage.py', 'createsuperuser'])
        else:
            self._run_cmd(['docker-compose', 'exec', 'app',
                          'python', 'manage.py', 'createsuperuser'])

    def run_tests(self):
        if self.args.dev:
            raise ValueError('For development environment tests, use '
                             '"python thunorbld.py test"')
        else:
            self._run_cmd(['docker-compose', 'run', '--rm',
                           '-e', 'THUNORHOME=/thunor',
                           'app',
                           'python', 'manage.py', 'test'])

    def thunorweb_version(self):
        cmd = ['python', '-c',
               'from thunorweb import __version__;print(__version__)']
        if self.args.dev:
            return self._run_cmd(cmd)

        cmd = ['docker-compose', 'exec', 'app'] + cmd
        if self._run_cmd(cmd, exit_on_error=False) != 0:
            raise RuntimeError('Command failed. Please check you\'ve started '
                               'Thunor Web with "docker-compose up -d".')

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
        parser_thunor_purge.add_argument('--verbosity', type=int,
                                         default=0)
        parser_thunor_purge.set_defaults(func=self.thunorweb_purge)

        parser_upgrade = subparsers.add_parser(
            'upgrade', help='Upgrade Thunor Web. Equivalent to makestatic, '
                            'migrate, and build called '
                            'sequentially.'
        )
        parser_upgrade.set_defaults(func=self.thunorweb_upgrade)

        parser_renew_certs = subparsers.add_parser(
            'renewcerts', help='Renew TLS certificates'
        )
        parser_renew_certs.set_defaults(func=self.renew_certificates)

        parser_deploy = subparsers.add_parser(
            'deploy', help='Generate example configuration and start Thunor Web'
        )
        parser_deploy.add_argument(
            '--hostname',
            help='Hostname for the server (defaults to "localhost", or the '
                 'server\'s IP address on Docker Machine). If not specified, '
                 'an interactive prompt will be used.'
        )
        parser_deploy.add_argument(
            '--thunorhome',
            help='(Docker Machine installs only) Installation directory for '
                 'Thunor Web on the *remote* machine.'
        )
        parser_deploy.set_defaults(func=self.deploy)

        parser_superuser = subparsers.add_parser(
            'createsuperuser', help='Create a Thunor Web admin account'
        )
        parser_superuser.set_defaults(func=self.createsuperuser)

        parser_test = subparsers.add_parser(
            'test', help='Run Thunor Web test suite'
        )
        parser_test.set_defaults(func=self.run_tests)

        parser_version = subparsers.add_parser(
            'version', help='Print the Thunor Web version and exit'
        )
        parser_version.set_defaults(func=self.thunorweb_version)

        return parser


if __name__ == '__main__':
    thunorctl = ThunorCtl()
    parser = thunorctl._parser()
    parser_args = parser.parse_args()
    thunorctl._set_args(parser_args)
    if hasattr(parser_args, 'func'):
        parser_args.func()
