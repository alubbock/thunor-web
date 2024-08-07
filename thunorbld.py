import argparse
import os
from thunorweb import __version__ as thunorweb_version
from thunorctl import ThunorCmdHelper


class ThunorBld(ThunorCmdHelper):
    _DEFAULT_TAGS = 'alubbock/thunorweb:dev'

    def __init__(self):
        super(ThunorBld, self).__init__()
        self.cwd = os.path.abspath(os.path.dirname(__file__))
        self.deploy_dir = os.path.join(self.cwd, '_state/deploy-test')
        self.buildx_archs = 'linux/amd64,linux/arm64'

    def _build_webpack(self):
        self._log.info('Build webpack container')
        return self._run_cmd(['docker', 'build', '-t', 'thunorweb_webpack',
                              'thunorweb/webpack'])

    @property
    def _volume_webpack_bundles(self):
        return os.path.join(
            self.cwd if self.args.dev else self.deploy_dir,
            '_state/webpack-bundles'
        ) + ':/thunor/_state/webpack-bundles'

    @property
    def _volume_webpack_static(self):
        return os.path.join(
            self.cwd if self.args.dev else self.deploy_dir,
            '_state/thunor-static-build'
        ) + ':/thunor/_state/thunor-static'

    @property
    def _volume_thunor_files(self):
        return os.path.join(
            self.cwd if self.args.dev else self.deploy_dir,
            '_state/thunor-files'
        ) + ':/thunor/_state/thunor-files'

    def generate_static(self):
        self._build_webpack()
        cmd = ['docker', 'run', '--rm']
        if self.args.dev:
            cmd += ['-e', 'DJANGO_DEBUG=True']
        cmd += ['-v', self._volume_webpack_bundles, 'thunorweb_webpack']
        self._log.info('Generate static files')
        return self._run_cmd(cmd)

    # def _init_buildx(self):
    #     self._log.info("Init docker buildx")
    #     return self._run_cmd([
    #         'docker', 'buildx', 'create', '--name', 'thunorbuild', '--use', '--append'
    #     ])

    # def _deinit_buildx(self):
    #     self._log.info("Deinit docker buildx")
    #     return self._run_cmd([
    #         'docker', 'buildx', 'rm', 'thunorbuild'
    #     ])

    def _build_base_image(self):
        self._log.info('Build thunorweb_base image')
        base_cmd = ['docker']
        if self.args.use_buildx:
            base_cmd += ['buildx', 'build', '--platform=' + self.buildx_archs]
        else:
            base_cmd += ['build']
        return self._run_cmd(base_cmd +
                             ['-t',
                              'thunorweb_base',
                              '--target',
                              'thunorweb_base',
                              '--build-arg',
                              'THUNORWEB_VERSION={}'.format(
                                  thunorweb_version),
                              self.cwd])

    def collect_static(self):
        cmd = ['python', 'manage.py', 'collectstatic', '--no-input']

        if not self.args.dev:
            self._log.debug('Collect static not used in non-dev mode')
            return True

        self._log.info('Collect static files')
        return self._run_cmd(cmd)

    def make_static(self):
        self.generate_static()
        self.collect_static()

    def thunorweb_build(self):
        if self.args.dev:
            raise ValueError('Cannot build Docker container in dev mode')

        # self.make_static()
        self.generate_static()
        self._log.info('Build main container')
        base_cmd = ['docker']
        if self.args.use_buildx:
            base_cmd += ['buildx', 'build', '--platform=' + self.buildx_archs]
        else:
            base_cmd += ['build']
        if self.args.push:
            base_cmd += ['--push']
        for tag in self.args.tags.split(','):
            base_cmd += ['-t', tag]
        self._run_cmd(base_cmd +
                      ['--build-arg',
                       'THUNORWEB_VERSION={}'.format(
                            thunorweb_version),
                       self.cwd])
        if 'cleanup' in self.args and self.args.cleanup:
            self._rmdir('_state/thunor-static-build')

    def _init_test_files(self):
        self._log.info('Initialize staging environment files')
        self._mkdir(self.deploy_dir)
        self._prepare_deployment_common(self.deploy_dir)
        self._copy('config-examples/nginx.site-basic.conf',
                   os.path.join(self.deploy_dir,
                                '_state/nginx-config/nginx.site.conf'))
        self._copy('config-examples/docker-compose.complete.yml',
                   os.path.join(self.deploy_dir,
                                'docker-compose.yml'))
        self._copy('docker-compose.services.yml',
                   os.path.join(self.deploy_dir, 'docker-compose.services.yml'))
        self._replace_in_file(
            os.path.join(self.deploy_dir, 'docker-compose.services.yml'),
            'image: alubbock/thunorweb:latest',
            'image: alubbock/thunorweb:dev'
        )

    def init_test(self):
        """ Minimal init for unit testing/CI purposes """
        self._init_test_files()
        self.args.use_buildx = False
        self.args.tags = self._DEFAULT_TAGS
        self.args.push = False
        self.thunorweb_build()

    def run_tests(self):
        if self.args.dev:
            self._log.info('Run tests (dev environment)')
            self._run_cmd(['coverage', 'run', 'manage.py', 'test'])
        else:
            compose_file = os.path.join(self.deploy_dir,
                                        'docker-compose.yml')
            base_cmd = ['docker', 'compose', '-f', compose_file]
            self._log.info('Start database (if not already up)')
            self._run_cmd(base_cmd + ['up', '-d', 'postgres', 'redis'])
            self._wait_postgres(compose_file=compose_file)
            try:
                self._log.info('Run tests (staging environment)')
                self._run_cmd(base_cmd + ['run', '--rm',
                                          '-e', 'THUNORHOME=/thunor',
                                          'app',
                                          'python', 'manage.py', 'test'])
            finally:
                self._log.info('Shutdown and clean up containers')
                self._run_cmd(base_cmd + ['down', '-v'])

    def init_dev(self):
        """ Initialise development environment """
        self.args.dev = True
        self._check_docker_compose()

        if os.path.exists(os.path.join(self.cwd, '_state')):
            raise ValueError('_state directory already exists. Is Thunor Web '
                             'already installed?')

        self._log.info('Initialize dev environment files')
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

        self._log.info('Start database')
        self._run_cmd(['docker', 'compose', 'up', '-d', 'postgres'])

        # Install Python reqs
        self._log.info('Install python requirements')
        self._run_cmd(['pip', 'install', '-r', 'requirements-dev.txt'])

        # Build static files
        self.make_static()

        self._wait_postgres()

        self._log.info('Migrate database')
        self._run_cmd(['python', 'manage.py', 'migrate'])

        self._log.info('Create database cache table')
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
        parser.add_argument('--debug', action='store_true', default=False,
                            help='Debug mode (increase verbosity)')
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
        parser_build.add_argument('--use-buildx', action='store_true', default=False,
                            help='Use docker buildx for cross-platform builds')
        parser_build.add_argument('--push', action='store_true', default=False,
                            help='Push to repo after build')
        parser_build.add_argument('--tags', default=ThunorBld._DEFAULT_TAGS,
                            help='Tags to use when building container (comma separated)')
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
    try:
        if hasattr(parser_args, 'func'):
            parser_args.func()
    finally:
        pass
