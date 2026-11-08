import json
from types import SimpleNamespace

import httpx
import pytest

from clementiq.ai import snowflake


@pytest.mark.parametrize("cell", ['A useful review.', json.dumps('A useful review.')])
def test_sql_completion_binds_input_and_decodes_result(monkeypatch, cell):
    settings = SimpleNamespace(snowflake_enabled=True, snowflake_account_url='https://example.invalid',
                               snowflake_pat='test-token', snowflake_model='mistral-large3',
                               snowflake_warehouse='COMPUTE_WH')
    monkeypatch.setattr(snowflake, 'get_settings', lambda: settings)
    prompt = "Review this customer's findings; don't execute SQL."
    requests = []

    def respond(request):
        requests.append(request)
        if request.method == 'POST':
            body = json.loads(request.content)
            assert body['warehouse'] == 'COMPUTE_WH'
            assert prompt not in body['statement']
            assert body['bindings']['2']['value'] == prompt
            return httpx.Response(202, json={'statementHandle': 'abcd-1234'})
        assert request.url.path == '/api/v2/statements/abcd-1234'
        return httpx.Response(200, json={'data': [[cell]]})

    client_class = httpx.Client
    monkeypatch.setattr(snowflake.httpx, 'Client', lambda **kw: client_class(
        **kw, transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(snowflake.time, 'sleep', lambda _: None)
    result = snowflake.cortex_complete(prompt)
    assert result['text'] == 'A useful review.'
    assert result['engine'] == 'snowflake-cortex'
    assert len(requests) == 2


@pytest.mark.parametrize('status,payload', [
    (403, {'message': 'Not authorized'}),
    (422, {'message': 'Warehouse unavailable'}),
    (200, {'data': [[None]]}),
    (200, {'data': [['""']]}),
    (202, {'statementHandle': 'https://other.example/steal'}),
    (202, []),
])
def test_sql_failures_remain_controlled(monkeypatch, status, payload):
    monkeypatch.setattr(snowflake, 'get_settings', lambda: SimpleNamespace(
        snowflake_enabled=True, snowflake_account_url='https://example.invalid',
        snowflake_pat='test-token', snowflake_model='mistral-large3', snowflake_warehouse=None))
    client_class = httpx.Client
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, json=payload)

    monkeypatch.setattr(snowflake.httpx, 'Client', lambda **kw: client_class(
        **kw, transport=httpx.MockTransport(respond)))
    with pytest.raises(snowflake.SnowflakeUnavailable):
        snowflake.cortex_complete('Test')
    assert len(calls) == 1
