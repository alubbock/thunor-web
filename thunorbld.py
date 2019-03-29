import argparse
import os
import sys
import time
from thunorweb import __version__ as thunorweb_version
from thunorctl import ThunorCmdHelper


class ThunorBld(ThunorCmdHelper):
    def __init__(self):
        super(ThunorBld, self).__init__()
        self.cwd = os.path.abspath(os.path.dirname(__file__))

    def _build_webpack(self):
        return self._run_cmd(['docker', 'build', '-t', 'thunorweb_webpack',
                              'thunorweb/webpack'])

    @property
    def _volume_webpack_bundles(self):
        return os.path.join(self.cwd, '_state/webpack-bundles') + \
                            ':/thunor/_state/webpack-bundles'

    @property
    def _volume_webpack_static(self):
        return os.path.join(self.cwd, '_state/thunor-static-build') + \
                            ':/thunor/_state/thunor-static'

    @property
    def _volume_thunor_files(self):
        return os.path.join(self.cwd, '_state/thunor-files') + \
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
            try:
                self._mkdir('_state/thunor-static-build')
            except FileExistsError:
                pass
            self._copy('config-examples/502.html',
                       '_state/thunor-static-build/502.html', overwrite=True)
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

    def _init_test_files(self):
        self._prepare_deployment_common()
        self._copy('config-examples/nginx.site-basic.conf',
                   '_state/nginx-config/nginx.site.conf')
        self._copy('config-examples/docker-compose.complete.yml',
                   'docker-compose.test-deploy.yml')

        self._replace_in_file('docker-compose.test-deploy.yml',
                              'alubbock/thunorweb:latest',
                              'alubbock/thunorweb:dev')
        self._replace_in_file(
            'docker-compose.test-deploy.yml',
            '_state/postgres-data',
            '_state/postgres-data-testdeploy'
        )

    def init_test(self):
        """ Minimal init for unit testing/CI purposes """
        self._init_test_files()
        self.thunorweb_build()

    def run_tests(self):
        if self.args.dev:
            self._run_cmd(['python', 'manage.py', 'test'])
        else:
            compose_file = 'docker-compose.test-deploy.yml'
            base_cmd = [
                'docker-compose', '-f',
                os.path.join(self.cwd, compose_file)
            ]
            self._run_cmd(base_cmd + ['up', '-d', 'postgres', 'redis'])
            self._wait_postgres(compose_file=compose_file)
            try:
                self._run_cmd(base_cmd + ['run', '--rm', 'app',
                                          'python', 'manage.py', 'test'])
            finally:
                self._run_cmd(base_cmd + ['down'])

    def init_dev(self):
        """ Initialise development environment """
        self._check_docker_compose()

        if os.path.exists(os.path.join(self.cwd, '_state')):
            raise ValueError('_state directory already exists. Is Thunor Web '
                             'already installed?')

        # Dev config
        self._copy('config-examples/thunor-dev.env', 'thunor-dev.env')
        self._generate_random_key('thunor-dev.env', '{{DJANGO_SECRET_KEY}}')
        self._generate_random_key('thunor-dev.env', '{{POSTGRES_PASSWORD}}')
        self._copy('config-examples/docker-compose.postgresonly.yml',
                   'docker-compose.yml')

        self._replace_in_file(
            os.path.join(self.cwd, 'docker-compose.yml'),
            '- thunor-db.env',
            '- thunor-dev.env'
        )
        self._init_test_files()

        # Both
        self._mkdir('_state/postgres-data')

        # Build static files
        self.make_static()

        self._run_cmd(['docker-compose', 'up', '-d', 'postgres'])

        # Install Python reqs
        self._run_cmd(['pip', 'install', '-r', 'requirements-dev.txt'])

        self._run_cmd(['python', 'manage.py', 'migrate'])

        self._run_cmd(['python', 'manage.py', 'createcachetable'])

        print('\nQuickstart complete! Next steps:')

        print('* Create an admin account with '
              '"python thunorctl.py createsuperuser"')

        print('* Run "python manage.py runserver" to start the development '
              'server')

    def _parser(self):
        parser = argparse.ArgumentParser(prog='thunorctl.py')
        parser.add_argument('--dev', action='store_true',
                            help='Developer mode (app runs outside of Docker)')
        parser.add_argument('--dry-run', action='store_true', default=False,
                            help='Dry run (don\'t execute any commands, '
                                 'just show them)')

        subparsers = parser.add_subparsers()

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

        parser_build = subparsers.add_parser(
            'build', help='Build Thunor Web Docker container'
        )
        parser_build.add_argument(
            '--cleanup', action='store_true', default=False,
            help='Cleanup intermediate build files'
        )
        parser_build.set_defaults(func=self.thunorweb_build)

        parser_init = subparsers.add_parser(
            'init', help='Generate example configuration and prepare '
                         'development environment'
        )
        parser_init.set_defaults(func=self.init_dev)

        parser_test_init = subparsers.add_parser(
            'testinit', help='Generate an environment for testing only. '
                             'Intended for continuous integration services.'
        )
        parser_test_init.set_defaults(func=self.init_test)

        parser_tests = subparsers.add_parser(
            'test', help='Run unit tests; use --dev flag to run outside of '
                         'Docker, or build Docker container first'
        )
        parser_tests.set_defaults(func=self.run_tests)

        parser.add_argument('--version', action='version',
                            version=thunorweb_version)

        return parser


if __name__ == '__main__':
    thunorbld = ThunorBld()
    parser = thunorbld._parser()
    parser_args = parser.parse_args()
    thunorbld._set_args(parser_args)
    if hasattr(parser_args, 'func'):
        parser_args.func()
