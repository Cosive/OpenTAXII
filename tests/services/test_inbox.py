import pytest

from libtaxii import messages_10 as tm10
from libtaxii import messages_11 as tm11
from libtaxii.constants import (
    ST_SUCCESS, ST_FAILURE, CB_STIX_XML_111, CB_STIX_XML_12)

from opentaxii.taxii import exceptions

from utils import prepare_headers, as_tm
from fixtures import (
    CUSTOM_CONTENT_BINDING, CONTENT, MESSAGE_ID,
    SERVICES, COLLECTIONS_A, COLLECTIONS_B,
    CONTENT_BINDING_SUBTYPE, INVALID_CONTENT_BINDING,
    COLLECTION_OPEN, COLLECTION_ONLY_STIX, COLLECTION_STIX_AND_CUSTOM,
    STIX_12_CONTENT, STIX_111_CONTENT
)


def make_content(version, content_binding=CUSTOM_CONTENT_BINDING,
                 content=CONTENT, subtype=None):
    if version == 10:
        return tm10.ContentBlock(content_binding, content)

    elif version == 11:
        content_block = tm11.ContentBlock(
            tm11.ContentBinding(content_binding), content)
        if subtype:
            content_block.content_binding.subtype_ids.append(subtype)

        return content_block
    else:
        raise ValueError('Unknown TAXII message version: %s' % version)


def make_inbox_message(version, blocks=None, dest_collection=None):

    if version == 10:
        inbox_message = tm10.InboxMessage(
            message_id=MESSAGE_ID,
            content_blocks=blocks
        )

    elif version == 11:
        inbox_message = tm11.InboxMessage(
            message_id=MESSAGE_ID,
            content_blocks=blocks
        )
        if dest_collection:
            inbox_message.destination_collection_names.append(dest_collection)
    else:
        raise ValueError('Unknown TAXII message version: %s' % version)

    return inbox_message


@pytest.fixture(autouse=True)
def prepare_server(server):
    server.persistence.create_services_from_object(SERVICES)

    from opentaxii.persistence.sqldb.models import DataCollection

    coll_mapping = {
        'inbox-A': COLLECTIONS_A,
        'inbox-B': COLLECTIONS_B
    }
    names = set()
    for service, collections in coll_mapping.items():
        for coll in collections:
            if coll.name not in names:
                coll = server.persistence.create_collection(coll)
                names.add(coll.name)
            else:
                coll = DataCollection.query.filter_by(name=coll.name).one()

            server.persistence.attach_collection_to_services(
                coll.id, service_ids=[service])


@pytest.mark.parametrize("https", [True, False])
@pytest.mark.parametrize("version", [11, 10])
def test_inbox_request_all_content(server, version, https):

    inbox_a = server.get_service('inbox-A')

    headers = prepare_headers(version, https)

    blocks = [
        make_content(
            version,
            content_binding=CUSTOM_CONTENT_BINDING,
            subtype=CONTENT_BINDING_SUBTYPE),
        make_content(
            version,
            content_binding=INVALID_CONTENT_BINDING)
    ]
    inbox_message = make_inbox_message(
        version,
        blocks=blocks
    )

    # "inbox-A" accepts all content
    response = inbox_a.process(headers, inbox_message)

    assert isinstance(response, as_tm(version).StatusMessage)

    assert response.status_type == ST_SUCCESS
    assert response.in_response_to == MESSAGE_ID

    blocks = server.persistence.get_content_blocks(None)
    assert len(blocks) == len(blocks)


@pytest.mark.parametrize("https", [True, False])
def test_inbox_request_destination_collection(server, https):
    version = 11

    inbox_message = make_inbox_message(
        version,
        blocks=[make_content(version)],
        dest_collection=None
    )
    headers = prepare_headers(version, https)

    inbox = server.get_service('inbox-A')
    # destination collection is not required for inbox-A
    response = inbox.process(headers, inbox_message)

    assert isinstance(response, as_tm(version).StatusMessage)
    assert response.status_type == ST_SUCCESS

    inbox = server.get_service('inbox-B')
    # destination collection is required for inbox-B
    with pytest.raises(exceptions.StatusMessageException):
        response = inbox.process(headers, inbox_message)


@pytest.mark.parametrize("https", [True, False])
@pytest.mark.parametrize("version", [11, 10])
def test_inbox_request_inbox_valid_content_binding(server, version, https):

    inbox = server.get_service('inbox-B')

    blocks = [
        make_content(
            version,
            content_binding=CUSTOM_CONTENT_BINDING,
            subtype=CONTENT_BINDING_SUBTYPE),
        make_content(
            version,
            content_binding=CB_STIX_XML_12)
    ]

    inbox_message = make_inbox_message(
        version,
        dest_collection=COLLECTION_OPEN,
        blocks=blocks
    )
    headers = prepare_headers(version, https)

    response = inbox.process(headers, inbox_message)

    assert isinstance(response, as_tm(version).StatusMessage)
    assert response.status_type == ST_FAILURE
    assert response.in_response_to == MESSAGE_ID

    # all blocks
    blocks = server.persistence.get_content_blocks(collection_id=None)
    assert len(blocks) == len(blocks)


@pytest.mark.parametrize("https", [True, False])
@pytest.mark.parametrize("version", [11, 10])
def test_inbox_req_inbox_invalid_inbox_content_binding(server, version, https):

    inbox = server.get_service('inbox-B')

    content = make_content(
        version,
        content_binding=INVALID_CONTENT_BINDING
    )
    inbox_message = make_inbox_message(
        version,
        dest_collection=COLLECTION_OPEN,
        blocks=[content]
    )

    headers = prepare_headers(version, https)

    response = inbox.process(headers, inbox_message)

    assert isinstance(response, as_tm(version).StatusMessage)
    assert response.status_type == ST_FAILURE
    assert response.in_response_to == MESSAGE_ID

    blocks = server.persistence.get_content_blocks(None)

    # Content blocks with invalid content should be ignored
    assert len(blocks) == 0


@pytest.mark.parametrize("https", [True, False])
@pytest.mark.parametrize("version", [11, 10])
def test_inbox_restricted_inbox_non_xml_data_as_stix(server, version, https):

    inbox = server.get_service('inbox-B')

    content = make_content(
        version,
        content="This is not XML",
        content_binding=CB_STIX_XML_12
    )
    inbox_message = make_inbox_message(
        version,
        dest_collection=COLLECTION_ONLY_STIX,
        blocks=[content]
    )

    headers = prepare_headers(version, https)

    response = inbox.process(headers, inbox_message)

    assert isinstance(response, as_tm(version).StatusMessage)
    assert response.status_type == ST_FAILURE
    assert response.in_response_to == MESSAGE_ID

    blocks = server.persistence.get_content_blocks(None)

    # Content blocks with invalid content should be ignored
    assert len(blocks) == 0


@pytest.mark.parametrize("https", [True, False])
@pytest.mark.parametrize("version", [11, 10])
def test_inbox_unresticted_inbox_non_xml_data(server, version, https):

    inbox = server.get_service('inbox-B')

    content = make_content(
        version,
        content="This is not XML",
        content_binding=CUSTOM_CONTENT_BINDING
    )
    inbox_message = make_inbox_message(
        version,
        dest_collection=COLLECTION_OPEN,
        blocks=[content]
    )

    headers = prepare_headers(version, https)

    response = inbox.process(headers, inbox_message)

    assert isinstance(response, as_tm(version).StatusMessage)
    assert response.status_type == ST_SUCCESS
    assert response.in_response_to == MESSAGE_ID

    blocks = server.persistence.get_content_blocks(None)

    # Content blocks with invalid content should be ignored
    assert len(blocks) == 1


@pytest.mark.parametrize("https", [True, False])
@pytest.mark.parametrize("version", [11, 10])
def test_inbox_restricted_inbox_non_stix_xml_as_stix(server, version, https):

    inbox = server.get_service('inbox-B')

    content = make_content(
        version,
        content=(
            "<?xml version='1.0' ?><!DOCTYPE root"
            " SYSTEM 'http://notstix.example.com'>"
            "<root><notstix></notstix></root>"
        ),
        content_binding=CB_STIX_XML_12
    )
    inbox_message = make_inbox_message(
        version,
        dest_collection=COLLECTION_OPEN,
        blocks=[content]
    )

    headers = prepare_headers(version, https)

    response = inbox.process(headers, inbox_message)

    assert isinstance(response, as_tm(version).StatusMessage)
    assert response.status_type == ST_FAILURE
    assert response.in_response_to == MESSAGE_ID

    blocks = server.persistence.get_content_blocks(None)

    # Content blocks with invalid content should be ignored
    assert len(blocks) == 0


@pytest.mark.parametrize("https", [True, False])
@pytest.mark.parametrize("version", [11, 10])
def test_inbox_restricted_inbox_stix12_as_stix12(server, version, https):

    inbox = server.get_service('inbox-B')

    content = make_content(
        version,
        content=STIX_12_CONTENT,
        content_binding=CB_STIX_XML_12
    )
    inbox_message = make_inbox_message(
        version,
        dest_collection=COLLECTION_ONLY_STIX,
        blocks=[content]
    )

    headers = prepare_headers(version, https)

    response = inbox.process(headers, inbox_message)

    assert isinstance(response, as_tm(version).StatusMessage)
    assert response.status_type == ST_SUCCESS
    assert response.in_response_to == MESSAGE_ID

    blocks = server.persistence.get_content_blocks(None)

    # Content blocks with invalid content should be ignored
    assert len(blocks) == 1


@pytest.mark.parametrize("https", [True, False])
@pytest.mark.parametrize("version", [11, 10])
def test_inbox_restricted_inbox_stix111_as_stix12(server, version, https):

    inbox = server.get_service('inbox-B')

    content = make_content(
        version,
        content=STIX_111_CONTENT,
        content_binding=CB_STIX_XML_12
    )
    inbox_message = make_inbox_message(
        version,
        dest_collection=COLLECTION_ONLY_STIX,
        blocks=[content]
    )

    headers = prepare_headers(version, https)

    response = inbox.process(headers, inbox_message)

    assert isinstance(response, as_tm(version).StatusMessage)
    assert response.status_type == ST_SUCCESS
    assert response.in_response_to == MESSAGE_ID

    blocks = server.persistence.get_content_blocks(None)

    # Content blocks with invalid content should be ignored
    assert len(blocks) == 1


@pytest.mark.parametrize("https", [True, False])
@pytest.mark.parametrize("version", [11, 10])
def test_inbox_restricted_inbox_stix12_as_stix111(server, version, https):

    inbox = server.get_service('inbox-B')

    content = make_content(
        version,
        content=STIX_12_CONTENT,
        content_binding=CB_STIX_XML_111
    )
    inbox_message = make_inbox_message(
        version,
        dest_collection=COLLECTION_ONLY_STIX,
        blocks=[content]
    )

    headers = prepare_headers(version, https)

    response = inbox.process(headers, inbox_message)

    assert isinstance(response, as_tm(version).StatusMessage)
    assert response.status_type == ST_FAILURE
    assert response.in_response_to == MESSAGE_ID

    blocks = server.persistence.get_content_blocks(None)

    # Content blocks with invalid content should be ignored
    assert len(blocks) == 0


@pytest.mark.parametrize("https", [True, False])
@pytest.mark.parametrize("version", [11, 10])
def test_inbox_restricted_inbox_stix111_as_stix111(server, version, https):

    inbox = server.get_service('inbox-B')

    content = make_content(
        version,
        content=STIX_111_CONTENT,
        content_binding=CB_STIX_XML_111
    )
    inbox_message = make_inbox_message(
        version,
        dest_collection=COLLECTION_ONLY_STIX,
        blocks=[content]
    )

    headers = prepare_headers(version, https)

    response = inbox.process(headers, inbox_message)

    assert isinstance(response, as_tm(version).StatusMessage)
    assert response.status_type == ST_SUCCESS
    assert response.in_response_to == MESSAGE_ID

    blocks = server.persistence.get_content_blocks(None)

    # Content blocks with invalid content should be ignored
    assert len(blocks) == 1


@pytest.mark.parametrize("https", [True, False])
@pytest.mark.parametrize("version", [11, 10])
def test_inbox_req_coll_content_bindings_filtering(server, version, https):

    inbox = server.get_service('inbox-B')
    headers = prepare_headers(version, https)

    blocks = [
        make_content(
            version,
            content="This is not XML",
            content_binding=CUSTOM_CONTENT_BINDING
        ),
        make_content(
            version,
            content="This is not XML",
            content_binding=INVALID_CONTENT_BINDING
        ),
    ]

    import pprint
    pprint.pprint(blocks)

    inbox_message = make_inbox_message(
        version, dest_collection=COLLECTION_STIX_AND_CUSTOM, blocks=blocks)

    response = inbox.process(headers, inbox_message)

    assert isinstance(response, as_tm(version).StatusMessage)
    assert response.status_type == ST_FAILURE
    assert response.in_response_to == MESSAGE_ID

    blocks = server.persistence.get_content_blocks(None)

    # Content blocks with invalid content should be ignored
    assert len(blocks) == 1
