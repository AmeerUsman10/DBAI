import { MiroApi } from '@mirohq/miro-api';

// DBAI - MySQL AI with Miro visualization
const api = new MiroApi(process.env.MIRO_TOKEN || '');

console.log('DBAI initialized. Miro API client ready.');

export { api };
