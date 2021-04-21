import argparse
import subprocess
import os
import sys
import shutil
import random
import time
import re
import logging


class ThunorCmdHelper(object):
    def __init__(self):
        self.cwd = os.path.abspath(os.path.dirname(__file__))

    def _set_args(self, args):
        self.args = args

        # Enable logging
        log_level = logging.DEBUG if self.args.debug else logging.INFO

        self._log = logging.getLogger(self.__class__.__name__)
        self._log.setLevel(log_level)
        ch = logging.StreamHandler()
        ch.setLevel(log_level)
        fmt = logging.Formatter(
            '%(name)s [%(levelname)s] %(message)s'
        )
        ch.setFormatter(fmt)
        self._log.addHandler(ch)

        if self.args.dry_run:
            self._log.warning('DRY RUN (no commands will be executed)')

    def _run_cmd(self, cmd, exit_on_error=True, capture_output=False):
        self._log.debug('Command: ' + (' '.join(cmd)))
        if self.args.dry_run:
            return 0
        env = os.environ.copy()
        env['COMPOSE_INTERACTIVE_NO_CLI'] = '1'
        p = subprocess.Popen(
            cmd, cwd=self.cwd, env=env,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None
        )
        p.wait()
        result = p.returncode
        if exit_on_error and result != 0:
            self._log.error(
                'Process exited with status {}, '
                'aborting...'.format(result)
            )
            sys.exit(result)
        return result

    def _copy(self, fromfile, tofile, overwrite=False):
        fromfile = os.path.join(self.cwd, fromfile)
        if not tofile.startswith('/'):
            tofile = os.path.join(self.cwd, tofile)
        self._log.debug('Copy: ' + fromfile + ' to ' + tofile)
        if self.args.dry_run:
            return
        if not overwrite and os.path.exists(tofile):
            self._log.error('Destination file exists, aborting...')
            sys.exit(1)
        shutil.copy2(fromfile, tofile)

    def _mkdir(self, dirname):
        if not dirname.startswith('/'):
            dirname = os.path.join(self.cwd, dirname)
        self._log.debug('Mkdir: ' + dirname)
        if self.args.dry_run:
            return
        os.makedirs(dirname)

    def _rmdir(self, dirname):
        dirname = os.path.join(self.cwd, dirname)
        self._log.debug('Delete: ' + dirname)
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

    def _check_docker_running(self):
        try:
            res = self._run_cmd(['docker', 'ps', '-q'], exit_on_error=False,
                                capture_output=True)
        except FileNotFoundError:
            self._log.error(
                '"docker" command not found. Check that Docker is '
                'installed and available on the system path.'
            )
            sys.exit(1)
        if not res:
            return
        self._log.error(
            '"docker ps -q" returned an error (exit code: {}). Is Docker '
            'running?'.format(res)
        )
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
        self._log.debug('Keygen: {} in {}'.format(keyname, filename))
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
                 'exec', '-T', 'postgres', 'pg_isready'],
                exit_on_error=False) != 0 and pg_retry < pg_max_retry:
            print('Postgres not yet ready, sleeping {} seconds...'.format(
                pg_retry_delay
            ))
            pg_retry += 1
            time.sleep(pg_retry_delay)

        if pg_retry == pg_max_retry:
            print('Postgres not responding, exiting...')
            sys.exit(1)

    def _get_env(self, filename, key):
        # Extract environment variable from .env file
        with open(os.path.join(self.cwd, filename), 'r') as f:
            app_env = f.read()

        match = re.search('^{}=(.*)$'.format(key), app_env, flags=re.MULTILINE)
        if not match:
            raise KeyError('{} not found in {}'.format(key, filename))

        value = match.group(1)
        self._log.debug('{} set to: {}'.format(key, value))

        return value

    def _append_env(self, env_var):
        env_val = os.environ.get(env_var, '')
        env_str = '{}={}'.format(env_var, env_val)

        env_file = os.path.join(self.cwd, '.env')
        self._log.debug('Append: "{}" to {}'.format(env_str, env_file))

        if self.args.dry_run:
            return

        with open(env_file, 'a') as f:
            f.write(env_str + '\n')


class ThunorCtl(ThunorCmdHelper):
    MAIN_CONTAINER_IMAGE = 'alubbock/thunorweb:latest'
    MAIN_CONTAINER_SERVICE = 'app'

    def migrate(self):
        self._log.info('Migrate database')
        if self.args.dev:
            return self._run_cmd(['python', 'manage.py', 'migrate'])
        else:
            return self._run_cmd(['docker-compose', 'run', '--rm',
                                  self.MAIN_CONTAINER_SERVICE,
                                  'python', 'manage.py', 'migrate'])

    def thunorweb_upgrade(self):
        if self.args.dev:
            self._log.info('Upgrade Thunor Web (dev mode)')
            from thunorbld import ThunorBld
            bld = ThunorBld()
            bld._set_args(self.args)
            bld.make_static()
        else:
            if self.args.all:
                self._log.info('Pull latest images for Thunor Web & services')
                self._run_cmd(['docker-compose', 'pull'])
            else:
                self._log.info('Pull latest image for Thunor Web')
                self._run_cmd(['docker-compose', 'pull',
                               self.MAIN_CONTAINER_SERVICE])
                active_image_hash = subprocess.check_output(
                    ['docker-compose', 'images', '-q',
                     self.MAIN_CONTAINER_SERVICE]).decode('utf8').strip()
                latest_image_hash = subprocess.check_output(
                    ['docker', 'images', '-q', self.MAIN_CONTAINER_IMAGE]
                ).decode('utf8').strip()
                if active_image_hash.find(latest_image_hash) == 0:
                    self._log.info('Latest version is already running')
                    return
            self.restart()
        self.migrate()
        self._log.info('Upgrade complete')

    def thunorweb_purge(self):
        self._log.info('Thunor Web purge')
        cmd = ['python', 'manage.py', 'thunor_purge']
        if self.args.verbosity > 0:
            cmd += ['--verbosity={}'.format(self.args.verbosity)]
        if self.args.dry_run:
            cmd += ['--dry-run']

        if not self.args.dev:
            cmd = ['docker-compose',
                   'run',
                   '--rm',
                   self.MAIN_CONTAINER_SERVICE] + cmd

        return self._run_cmd(cmd)

    @property
    def _certbot_cmd(self):
        return ['docker-compose', '-f',
                os.path.join(self.cwd, 'docker-compose.certbot.yml'),
                'run', '--rm', 'certbot']

    def _generate_dhparams(self):
        self._log.info('Check for Diffie-Hellman parameter file')
        # Does dhparams.pem file already exist?
        file_exists = self._run_cmd(
            self._certbot_cmd +
            ['test', '-f', '/etc/letsencrypt/dhparams.pem'],
            exit_on_error=False
        ) == 0
        if file_exists:
            self._log.debug('Thunorctl: dhparams.pem file exists, skipping...')
            return
        self._log.info('Generate Diffie-Hellman parameter file')

        self._run_cmd(
            self._certbot_cmd + ['openssl', 'dhparam', '-out',
                                 '/etc/letsencrypt/dhparams.pem', '2048']
        )

    def _generate_certificate(self, hostname=None):
        self._log.info('Generate certificate using certbot')
        cmd = self._certbot_cmd + [
            'certbot', 'certonly', '--webroot', '--webroot-path',
            '/thunor-static']
        if hostname:
            cmd += ['-d', hostname]
        if 'letsencrypt_args' in self.args:
            cmd += self.args.letsencrypt_args
        return self._run_cmd(cmd)

    def _prompt_hostname(self, default='localhost'):
        hostname = input('\nEnter a hostname (default: {}) : '.format(default)
                         ).strip()
        if not hostname:
            hostname = default
        return hostname

    def _deploy_tls_config(self, hostname):
        # Proceed with TLS deployment
        self._log.info('Deploy TLS configuration to NGINX')
        self._copy('config-examples/nginx.site-full.conf',
                   '_state/nginx-config/nginx.site.conf',
                   overwrite=True)
        self._replace_in_file(
            os.path.join(self.cwd, '_state/nginx-config/nginx.site.conf'),
            '{{SERVER_NAME}}',
            hostname
        )
        thunorhome = self._get_env('.env', 'THUNORHOME')
        if 'DOCKER_MACHINE_NAME' in os.environ:
            self._run_cmd([
                'docker-machine', 'scp',
                '_state/nginx-config/nginx.site.conf',
                '{}:{}/_state/nginx-config/nginx.site.conf'.format(
                    os.environ['DOCKER_MACHINE_NAME'],
                    thunorhome
                )
            ])
            self._run_cmd([
                'docker-machine', 'scp',
                'config-examples/renew-certs.sh',
                '{}:{}/renew-certs.sh'.format(
                    os.environ['DOCKER_MACHINE_NAME'],
                    thunorhome
                )
            ])
        self._log.info('Trigger NGINX reload')
        self._run_cmd(['docker-compose', 'exec', 'nginx', 'nginx', '-s',
                       'reload'])
        self._log.info('Set DJANGO_ACCOUNTS_TLS=True')
        self._replace_in_file(
            os.path.join(self.cwd, 'thunor-app.env'),
            'DJANGO_ACCOUNTS_TLS=False',
            'DJANGO_ACCOUNTS_TLS=True'
        )
        self._log.info('Restart app container')
        self._run_cmd(['docker-compose', 'restart',
                       self.MAIN_CONTAINER_SERVICE])

    def generate_certificates(self, prompt=True):
        try:
            hostname = self._get_env('thunor-app.env', 'DJANGO_HOSTNAME')
        except (FileNotFoundError, KeyError):
            hostname = self._prompt_hostname()
        if hostname == 'localhost':
            raise ValueError('Cannot generate TLS certificates for localhost.'
                             'Please use a publicly accessible DNS name.')
        self._generate_dhparams()
        self._generate_certificate(hostname)
        if prompt:
            print('\nAutomatically update NGINX configuration (recommended)?')
            print('This will overwrite your nginx.site.conf file')
            print('That is not a problem unless you made manual changes to '
                  'that file')
            response = ''
            while response not in ('y', 'n'):
                response = input('\nContinue (Y/N)? ').lower()

            if response == 'n':
                print('Please manually update your nginx.site.conf file '
                      'to enable TLS')
                print('Use config-examples/nginx.site-full.conf as an example')
                print('Then restart to load the new configuration')
                return
        self._deploy_tls_config(hostname)
        self._log.info('TLS successfully enabled')

    def renew_certificates(self):
        self._log.info('Renew certificate using letsencrypt')
        self._run_cmd(self._certbot_cmd +
                      ['certbot', 'renew', '--non-interactive'])

        self._log.info('Trigger NGINX reload')
        self._run_cmd(['docker-compose', 'exec', 'nginx', 'nginx',
                       '-s', 'reload'])

    def deploy(self):
        self._log.info('Deployment start, checking prerequisites')
        if self.args.dev:
            raise ValueError('Deployment not available/needed in dev mode')

        if os.path.exists(os.path.join(self.cwd, '_state')):
            raise ValueError('_state directory already exists. Is Thunor Web '
                             'already installed, or did a previous installation'
                             ' fail? Remove the _state directory to re-deploy '
                             'Thunor Web (warning - data loss!)')

        self._check_docker_compose()
        self._check_docker_running()

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

        if not self.args.hostname:
            self.args.hostname = self._prompt_hostname(
                default=docker_ip if docker_ip else 'localhost')

        if self.args.enable_tls and self.args.hostname in \
                ('localhost', docker_ip):
            raise ValueError('Cannot use --enable-tls without a web accessible '
                             'hostname.')

        if docker_machine:
            self._replace_in_file(
                os.path.join(self.cwd, '.env'),
                'THUNORHOME=.',
                'THUNORHOME={}'.format(self.args.thunorhome)
            )
            self._append_env('DOCKER_TLS_VERIFY')
            self._append_env('DOCKER_HOST')
            self._append_env('DOCKER_CERT_PATH')

            self._run_cmd(['docker-machine', 'ssh', docker_machine,
                           'mkdir', '"' + self.args.thunorhome + '"'])
        elif self.args.thunorhome:
            raise ValueError('--thunorhome set, but Docker Machine is '
                             'not active. Have you activated the machine\'s '
                             'environment? If you\'re attempting a local '
                             'installation, this option is not needed.')

        self._log.info('Deploying configuration files')

        self._prepare_deployment_common()
        self._copy('config-examples/docker-compose.complete.yml',
                   'docker-compose.yml')

        self._copy('config-examples/nginx.site-basic.conf',
                   '_state/nginx-config/nginx.site.conf')

        self._mkdir('_state/postgres-data')

        self._log.debug('Set DJANGO_HOSTNAME in thunor-app.env to {}'.format(
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

        self._log.info('Starting database')
        self._run_cmd(['docker-compose', 'up', '-d', 'postgres'])

        if not self.args.dry_run:
            self._wait_postgres()

        self.migrate()

        self.start()

        if self.args.enable_tls:
            self.generate_certificates(prompt=False)

        print('\nDeploy complete! Thunor should be available at http://{}\n'
              .format(self.args.hostname))

        print('Next steps:')
        print('* Create an admin account with '
              '"python thunorctl.py createsuperuser"')
        if not self.args.enable_tls:
            print('* Enable TLS encrypted connections with '
                  '"python thunorctl.py generatecerts"')

    def createsuperuser(self):
        self._log.info('Create superuser')
        if self.args.dev:
            self._run_cmd(['python', 'manage.py', 'createsuperuser'])
        else:
            self._run_cmd(['docker-compose', 'exec',
                           self.MAIN_CONTAINER_SERVICE,
                          'python', 'manage.py', 'createsuperuser'])

    def run_tests(self):
        if self.args.dev:
            raise ValueError('For development environment tests, use '
                             '"python thunorbld.py test"')
        else:
            self._log.info('Run test suite')
            self._run_cmd(['docker-compose', 'run', '--rm',
                           '-e', 'THUNORHOME=/thunor',
                           self.MAIN_CONTAINER_SERVICE,
                           'python', 'manage.py', 'test'])

    def start(self, log=True):
        if self.args.dev:
            raise ValueError('Not available in dev mode. Use '
                             '"python manage.py runserver".')
        if log:
            self._log.info('Start Thunor Web')
        self._run_cmd(['docker-compose', 'up', '-d'])

    def stop(self, log=True):
        if self.args.dev:
            raise ValueError('Not available in dev mode.')
        if log:
            self._log.info('Stop Thunor Web')
        self._run_cmd(['docker-compose', 'down', '-v'])

    def restart(self):
        self._log.info('Restart Thunor Web')
        self.stop(log=False)
        self.start(log=False)

    def thunorweb_version(self):
        cmd = ['python', '-c',
               'from thunorweb import __version__;print(__version__)']
        if self.args.dev:
            return self._run_cmd(cmd)

        cmd = ['docker-compose', 'exec', self.MAIN_CONTAINER_SERVICE] + cmd
        if self._run_cmd(cmd, exit_on_error=False) != 0:
            raise RuntimeError('Command failed. Please check you\'ve started '
                               'Thunor Web with "python thunorctl.py start".')

    def _parser(self):
        parser = argparse.ArgumentParser(prog='thunorctl.py')
        parser.add_argument('--dev', action='store_true',
                            help='Developer mode (app runs outside of Docker)')
        parser.add_argument('--dry-run', action='store_true', default=False,
                            help='Dry run (don\'t execute any commands, '
                                 'just show them)')
        parser.add_argument('--debug', action='store_true', default=False,
                            help='Debug mode (increase verbosity)')
        subparsers = parser.add_subparsers()

        # Deploy
        parser_deploy = subparsers.add_parser(
            'deploy', help='Generate configuration files and start Thunor Web'
        )
        parser_deploy.add_argument(
            '--hostname',
            help='Hostname for the server (defaults to "localhost", or the '
                 'server\'s IP address on Docker Machine). If not specified, '
                 'an interactive prompt will be used.'
        )
        parser_deploy.add_argument(
            '--enable-tls', action='store_true', default=False,
            help='Generate TLS certificates to encrypt connections using '
                 'certbot'
        )
        parser_deploy.add_argument(
            '--thunorhome',
            help='(Docker Machine installs only) Installation directory for '
                 'Thunor Web on the *remote* machine.'
        )
        parser_deploy.set_defaults(func=self.deploy)

        # Start, stop, restart
        parser_start = subparsers.add_parser(
            'start', help='Start Thunor Web (use "deploy" instead on first use)'
        )
        parser_start.set_defaults(func=self.start)
        parser_stop = subparsers.add_parser(
            'stop', help='Stop Thunor Web'
        )
        parser_stop.set_defaults(func=self.stop)
        parser_restart = subparsers.add_parser(
            'restart', help='Restart Thunor Web'
        )
        parser_restart.set_defaults(func=self.restart)

        # Upgrade
        parser_upgrade = subparsers.add_parser(
            'upgrade', help='Upgrade Thunor Web'
        )
        parser_upgrade.add_argument(
            '--all',
            help='Upgrade all services (NGINX, PostgreSQL, etc.), not just '
                 'Thunor Web itself',
            action='store_true',
            default=False
        )
        parser_upgrade.set_defaults(func=self.thunorweb_upgrade)

        # Generate certs
        parser_generate_certs = subparsers.add_parser(
            'generatecerts', help='Generate TLS certificates. Additional '
                                  'arguments are passed onto certbot.'
        )
        parser_generate_certs.add_argument('letsencrypt_args',
                                           nargs=argparse.REMAINDER)
        parser_generate_certs.set_defaults(func=self.generate_certificates)

        # Renew certs
        parser_renew_certs = subparsers.add_parser(
            'renewcerts', help='Renew TLS certificates'
        )
        parser_renew_certs.set_defaults(func=self.renew_certificates)

        parser_thunor_purge = subparsers.add_parser(
            'purge', help='Purge Thunor Web of temporary files to reclaim disk '
                          'space.'
        )
        parser_thunor_purge.add_argument('--verbosity', type=int,
                                         default=0)
        parser_thunor_purge.set_defaults(func=self.thunorweb_purge)

        parser_migrate = subparsers.add_parser(
            'migrate', help='Initialise or migrate the database')
        parser_migrate.set_defaults(func=self.migrate)

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
