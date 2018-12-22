import argparse
import subprocess
import os
import sys
import shutil

cwd = os.path.abspath(os.path.dirname(__file__))


def _run_cmd(cmd, thunorhome=None, exit_on_error=True):
    print('Thunorctl command: ' + (' '.join(cmd)))
    env = os.environ.copy()
    if thunorhome is not None:
        env['THUNORHOME'] = thunorhome
    result = subprocess.call(cmd, cwd=cwd, env=env)
    if exit_on_error and result != 0:
        print('Thunorctl: Process exited with status {}, aborting...'.format(
            result))
        sys.exit(result)
    return result


def _copy(fromfile, tofile):
    fromfile = os.path.join(cwd, fromfile)
    tofile = os.path.join(cwd, tofile)
    print('Thunorctl copy: ' + fromfile + ' to ' + tofile)
    if os.path.exists(tofile):
        print('Thunorctl: Destination file exists, aborting...')
        sys.exit(1)
    shutil.copy2(fromfile, tofile)


def _mkdir(dir):
    dir = os.path.join(cwd, dir)
    print('Thunorctl mkdir: ' + dir)
    os.makedirs(dir)


def _get_thunorhome(args):
    if args.thunorhome:
        thunorhome = args.thunorhome
    else:
        try:
            thunorhome = os.environ['THUNORHOME']
        except KeyError:
            raise ValueError('Set the THUNORHOME environment variable or use '
                             'the --thunorhome argument to set the path to '
                             'Thunor Web on the machine on which it is '
                             'running (usually, your local machine)')

    print('Thunorctl: THUNORHOME set to {}'.format(thunorhome))
    return thunorhome


def migrate(args):
    if args.dev:
        return _run_cmd(['python', 'manage.py', 'migrate'])
    else:
        return _run_cmd(['docker-compose', 'run', '--rm', 'app',
                         'python', 'manage.py', 'migrate'])


def _build_webpack():
    return _run_cmd(['docker', 'build', '-t', 'thunorweb_webpack',
                     'thunorweb/webpack'])


def _volume_webpack_bundles(thunorhome):
    return os.path.join(thunorhome, '_state/webpack-bundles') + \
        ':/thunor/_state/webpack-bundles'


def _volume_webpack_static(thunorhome):
    return os.path.join(thunorhome, '_state/thunor-static') + \
        ':/thunor/_state/thunor-static'


def generate_static(args):
    _build_webpack()
    cmd = ['docker', 'run', '--rm']
    if args.dev:
        cmd += ['-e', 'DJANGO_DEBUG=True']
        thunorhome = cwd
    else:
        thunorhome = _get_thunorhome(args)
    cmd += ['-v', _volume_webpack_bundles(thunorhome), 'thunorweb_webpack']
    return _run_cmd(cmd)


def collect_static(args):
    cmd = ['python', 'manage.py', 'collectstatic', '--no-input']

    if not args.dev:
        thunorhome = _get_thunorhome(args)
        cmd = ['docker-compose',
               'run',
               '--rm',
               '-v', _volume_webpack_bundles(thunorhome),
               '-v', _volume_webpack_static(thunorhome),
               'app'] + cmd

    return _run_cmd(cmd)


def make_static(args):
    generate_static(args)
    collect_static(args)


def thunorweb_upgrade(args):
    make_static(args)
    migrate(args)


def thunor_purge(args):
    cmd = ['python', 'manage.py', 'thunor_purge']
    if args.verbosity > 0:
        cmd += ['--verbosity={}'.format(args.verbosity)]
    if args.dry_run:
        cmd += ['--dry-run']

    if not args.dev:
        thunorhome = _get_thunorhome(args)
        cmd = ['docker-compose',
               'run',
               '--rm',
               '-v', _volume_webpack_bundles(thunorhome),
               '-v', _volume_webpack_static(thunorhome),
               'app'] + cmd

    return _run_cmd(cmd)


def _certbot_cmd():
    return ['docker-compose',
            '-f', os.path.join(cwd, 'docker-compose.certbot.yml'),
            'run', '--rm', 'certbot']


def _generate_dhparams(args):
    # Does dhparams.pem file already exist?
    thunorhome = _get_thunorhome(args)
    file_exists = _run_cmd(
        _certbot_cmd() + ['test', '-f', '/etc/letsencrypt/dhparams.pem'],
        thunorhome=thunorhome,
        exit_on_error=False
    ) == 0
    if file_exists:
        print('Thunorctl: dhparams.pem file exists, skipping...')
        return

    _run_cmd(
        _certbot_cmd() + ['openssl', 'dhparam', '-out',
                          '/etc/letsencrypt/dhparams.pem', '2048'],
        thunorhome=thunorhome
    )


def _generate_certificate(args):
    cmd = _certbot_cmd() + [
        'certbot', 'certonly', '--webroot', '--webroot-path',
        '/thunor-static'] + args.letsencrypt_args
    return _run_cmd(cmd, thunorhome=_get_thunorhome(args))


def generate_certificates(args):
    _generate_dhparams(args)
    _generate_certificate(args)


def renew_certificates(args):
    _run_cmd(_certbot_cmd() + ['certbot', 'renew', '--non-interactive'],
             thunorhome=_get_thunorhome(args)
             )

    _run_cmd(['docker-compose', 'exec', 'nginx', 'nginx', '-s', 'reload'])


def quickstart(args):
    _copy('config-examples/docker-compose.complete.yml', 'docker-compose.yml')
    _copy('config-examples/thunor-app.env', 'thunor-app.env')
    _copy('config-examples/thunor-db.env', 'thunor-db.env')
    _mkdir('_state/thunor-static')
    _copy('config-examples/502.html', '_state/thunor-static/502.html')
    _mkdir('_state/nginx-config')
    _copy('config-examples/nginx.base.conf',
          '_state/nginx-config/nginx.base.conf')
    _copy('config-examples/nginx.site-basic.conf',
          '_state/nginx-config/nginx.site.conf')

    print('Quickstart files in place. Be sure to edit the following files '
          'before proceeding:\n\n'
          ' * thunor-db.env     Database configuration\n'
          ' * thunor-app.env    Main configuration\n'
          )


def _parser():
    parser = argparse.ArgumentParser(prog='thunorctl.py')
    parser.add_argument('--dev', action='store_true',
                        help='Developer mode (don\'t use Docker)')
    parser.add_argument('--thunorhome', help='Path to Thunor Web on the '
                                             'target machine, or use '
                                             'environment variable THUNORHOME')
    subparsers = parser.add_subparsers()

    parser_migrate = subparsers.add_parser(
        'migrate', help='Initialise or migrate the database')
    parser_migrate.set_defaults(func=migrate)

    parser_make_static = subparsers.add_parser(
        'makestatic', help='Generate static files and collect them in '
                           'Django. Equivalent to generatestatic and '
                           'collectstatic called sequentially.'
    )
    parser_make_static.set_defaults(func=make_static)

    parser_generate_static = subparsers.add_parser(
        'generatestatic', help='Generate static files'
    )
    parser_generate_static.set_defaults(func=generate_static)

    parser_collect_static = subparsers.add_parser(
        'collectstatic', help='Collect static files in Django'
    )
    parser_collect_static.set_defaults(func=collect_static)

    parser_generate_certs = subparsers.add_parser(
        'generatecerts', help='Generate TLS certificates. Additional '
                              'arguments are passed onto letsencrypt.'
    )
    parser_generate_certs.add_argument('letsencrypt_args',
                                       nargs=argparse.REMAINDER)
    parser_generate_certs.set_defaults(func=generate_certificates)

    parser_thunor_purge = subparsers.add_parser(
        'purge', help='Purge Thunor Web of temporary files to reclaim disk '
                      'space.'
    )
    parser_thunor_purge.add_argument('--dry-run', action='store_true',
                                     default=False)
    parser_thunor_purge.add_argument('--verbosity', type=int,
                                     default=0)
    parser_thunor_purge.set_defaults(func=thunor_purge)

    parser_upgrade = subparsers.add_parser(
        'upgrade', help='Upgrade Thunor Web. Equivalent to makestatic and '
                        'migrate called sequentially.'
    )
    parser_upgrade.set_defaults(func=thunorweb_upgrade)

    parser_renew_certs = subparsers.add_parser(
        'renewcerts', help='Renew TLS certificates'
    )
    parser_renew_certs.set_defaults(func=renew_certificates)

    parser_quickstart = subparsers.add_parser(
        'skeleton', help='Create quickstart skeleton configuration files'
    )
    parser_quickstart.set_defaults(func=quickstart)

    return parser


if __name__ == '__main__':
    parser = _parser()
    args = parser.parse_args()
    if hasattr(args, 'func'):
        args.func(args)
