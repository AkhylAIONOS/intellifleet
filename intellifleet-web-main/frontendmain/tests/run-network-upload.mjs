import assert from 'node:assert/strict';
import {createServer} from 'vite';
const server=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try {
  const {formatUploadError}=await server.ssrLoadModule('/src/components/NetworkUpload.tsx');
  assert.match(formatUploadError({message:'Network Error'}), /backend is running.*frontend origin/);
  assert.match(formatUploadError({response:{status:401,data:{detail:'Token validation failed'}}}), /authentication required/);
  assert.match(formatUploadError({response:{status:403}}), /permission/);
  assert.equal(formatUploadError({response:{status:422,data:{detail:'Routes CSV contains unknown warehouse ID X'}}}), 'Routes CSV contains unknown warehouse ID X');
  assert.match(formatUploadError({response:{status:422,data:{detail:[{loc:['body','routes_csv'],msg:'Field required'}]}}}), /routes_csv: Field required/);
  assert.doesNotMatch(formatUploadError({response:{status:500,data:{detail:'secret stack trace'}}}), /secret|stack/);
  console.log('PASS: upload errors explain connection, auth, validation, and safe server failure');
} finally { await server.close(); }
