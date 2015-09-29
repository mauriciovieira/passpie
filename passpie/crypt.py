import os
import re
import shutil
import tempfile

from . import process
from .utils import logger, tempdir

from passpie.utils import which


GPG_HOMEDIR = os.path.expanduser('~/.gnupg')
DEVNULL = open(os.devnull, 'w')
KEY_INPUT = """Key-Type: RSA
Key-Length: {}
Subkey-Type: RSA
Name-Comment: Auto-generated by Passpie
Passphrase: {}
Name-Real: Passpie
Name-Email: passpie@local
Expire-Date: 0
%commit
"""


def make_key_input(passphrase, key_length):
    try:
        key_input = KEY_INPUT.format(key_length, passphrase)
    except UnicodeEncodeError:
        key_input = KEY_INPUT.format(passphrase.encode('utf-8'))
    return key_input


def export_keys(homedir, secret=False):
    command = [
        which('gpg2') or which('gpg'),
        '--no-version',
        '--batch',
        '--homedir', homedir,
        '--export-secret-keys' if secret else '--export',
        '--armor',
        '-o', '-'
    ]
    output, error = process.call(command)
    return output


def create_keys(passphrase, path=None, key_length=4096):
    with tempdir() as homedir:
        command = [
            which('gpg2') or which('gpg'),
            '--batch',
            '--no-tty',
            '--homedir', homedir,
            '--gen-key',
        ]
        key_input = make_key_input(passphrase, key_length)
        output, error = process.call(command, input=key_input)

        if path:
            keys_path = os.path.join(homedir, 'keys')
            with open(keys_path, 'w') as keysfile:
                keysfile.write(export_keys(homedir))
                keysfile.write(export_keys(homedir, secret=True))

            path = os.path.expanduser(path)
            os.rename(keys_path, os.path.join(path, '.keys'))
        else:
            return output


class GPG(object):

    def __init__(self, path, recipient=None):
        self.homedir = GPG_HOMEDIR
        self.homedir_is_temp = False
        self._recipient = recipient
        path = os.path.expanduser(path)
        self.keys_path = os.path.join(path, ".keys")
        if os.path.isfile(self.keys_path):
            self.homedir = tempfile.mkdtemp()
            self.homedir_is_temp = True
            self.path = self.homedir
            self.import_keys(self.keys_path)
        else:
            self.path = path

    def __enter__(self):
        logger.debug('__enter__: {}'.format(self))
        return self

    def __exit__(self, exc_ty, exc_val, exc_tb):
        if self.homedir and os.path.exists(self.homedir) and self.homedir_is_temp:
            logger.debug('__exit__: {}'.format(self))
            logger.debug('deleting: {}'.format(self.homedir))
            shutil.rmtree(self.homedir)

    def import_keys(self, keys_path):
        command = [
            which('gpg2') or which('gpg'),
            '--no-tty',
            '--homedir', self.homedir,
            '--import', self.keys_path
        ]
        output, error = process.call(command)
        return output

    def recipient(self, secret=False):
        if self._recipient:
            return self._recipient
        visibility = 'secret' if secret else 'public'
        command = [
            which('gpg2') or which('gpg'),
            '--no-tty',
            '--list-{}-keys'.format(visibility),
            '--fingerprint',
            '--homedir', self.homedir,
        ]
        output, error = process.call(command)
        if error:
            logger.debug(error)

        rgx = re.compile(r'(([0-9A-F]{4}\s*?){10})')
        for line in output.splitlines():
            print(line)
            mobj = rgx.search(line)
            if mobj:
                fingerprint = mobj.group().replace(' ', '')
                print(fingerprint)
                return fingerprint

        return ''

    def encrypt(self, data, fingerprint=None):
        command = [
            which('gpg2') or which('gpg'),
            '--batch',
            '--no-tty',
            '--always-trust',
            '--armor',
            '--recipient', self.recipient(),
            '--homedir', self.homedir,
            '--encrypt'
        ]
        output, error = process.call(command, input=data)
        if error:
            logger.debug(error)
        return output

    def decrypt(self, data, passphrase, fingerprint=None):
        command = [
            which('gpg2') or which('gpg'),
            '--batch',
            '--no-tty',
            '--always-trust',
            '--recipient', self.recipient(secret=True),
            '--homedir', self.homedir,
            '--passphrase', passphrase,
            '--emit-version',
            '-o', '-',
            '-d', '-',
        ]
        logger.debug('decrypting with: {}'.format(self))
        output, error = process.call(command, input=data)
        if error:
            logger.debug(error)
        return output

    def __str__(self):
        return "GPG(path={0.path}, homedir={0.homedir})".format(self)
