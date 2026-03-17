import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { MiroApi } from '@mirohq/miro-api';

describe('DBAI - Miro API', () => {
  it('should instantiate MiroApi without error', () => {
    const api = new MiroApi('test-token');
    assert.ok(api, 'MiroApi instance should be created');
  });

  it('should create MiroApi with empty token', () => {
    const api = new MiroApi('');
    assert.ok(api, 'MiroApi instance should be created with empty token');
  });
});
