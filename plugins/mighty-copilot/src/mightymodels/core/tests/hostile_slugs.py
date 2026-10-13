import pytest

from mightymodels.core.slug import SLUG_LIMIT

HOSTILE = [
    pytest.param('../outside', id='parent'),
    pytest.param('..', id='dot-dot'),
    pytest.param('a/../../b', id='nested-parent'),
    pytest.param('a/b', id='separator'),
    pytest.param('a\\b', id='backslash'),
    pytest.param('/etc', id='absolute'),
    pytest.param('.', id='dot'),
    pytest.param('.runtime', id='hidden'),
    pytest.param('a..b', id='inner-dots'),
    pytest.param('', id='empty'),
    pytest.param('a\n', id='trailing-newline'),
    pytest.param('a\x00b', id='nul'),
    pytest.param('-rf', id='option'),
    pytest.param('~root', id='tilde'),
    pytest.param('retry queue', id='space'),
    pytest.param('x' * (SLUG_LIMIT + 1), id='too-long'),
    pytest.param('archives', id='reserved'),
]
