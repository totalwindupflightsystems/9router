import { AI_PROVIDERS } from './src/shared/constants/providers.js';

const oai = AI_PROVIDERS['openai'];
console.log('openai entry keys:', oai ? Object.keys(oai).slice(0, 12) : 'ABSENT');
console.log('noAuth:', oai?.noAuth, '| category:', oai?.category);

// count credentialless
const credless = Object.entries(AI_PROVIDERS).filter(([, v]) => v?.noAuth === true).map(([k]) => k);
console.log('credentialless providers:', credless.length, credless.slice(0, 12).join(','));
