import pytest

from opentaxii.middleware import create_app
from opentaxii.utils import configure_logging
from opentaxii.config import load_configuration

from fixtures import DOMAIN


@pytest.fixture(autouse=True, scope='session')
def setup_logging():
    configure_logging({'': 'debug'})


def get_config_for_tests(domain=DOMAIN, persistence_db=None, auth_db=None):

    config = load_configuration()
    config.update({
        'persistence_api': {
            'class': 'opentaxii.persistence.sqldb.SQLDatabaseAPI',
            'parameters': {
                'db_connection': persistence_db or 'sqlite://',
                'create_tables': True
            }
        },
        'auth_api': {
            'class': 'opentaxii.auth.sqldb.SQLDatabaseAPI',
            'parameters': {
                'db_connection': auth_db or 'sqlite://',
                'create_tables': True,
                'secret': 'dummy-secret-string-for-tests'
            }
        },
        'domain': domain
    })
    return config


@pytest.fixture()
def config(request):
    return get_config_for_tests()


@pytest.fixture()
def client(server):
    app = create_app(server)
    app.config['TESTING'] = True
    return app.test_client()
