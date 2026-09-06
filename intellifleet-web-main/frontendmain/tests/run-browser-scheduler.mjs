import assert from 'node:assert/strict';
import {createServer} from 'vite';
const server=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try {
  const {playJourney}=await server.ssrLoadModule('/src/utils/journeyPlayback.ts');
  let frames=new Map(),id=0;
  // Chrome requires Window as the native method receiver; arrow mocks miss this.
  const browserWindow={
    requestAnimationFrame(callback){if(this!==browserWindow)throw new TypeError('Illegal invocation');frames.set(++id,callback);return id;},
    cancelAnimationFrame(handle){if(this!==browserWindow)throw new TypeError('Illegal invocation');frames.delete(handle);}
  };
  globalThis.window=browserWindow;
  globalThis.requestAnimationFrame=browserWindow.requestAnimationFrame;
  globalThis.cancelAnimationFrame=browserWindow.cancelAnimationFrame;
  const plan={mode:'road',route_legs:[{route_type:'road',source_coords:{lat:1,lng:2},destination_coords:{lat:3,lng:4}}],vehicles:[]};
  let positions=[];
  const cancel=playJourney(plan,p=>positions.push(p));
  assert.equal(frames.size,1);
  const advance=t=>{const pending=[...frames.values()];frames.clear();pending.forEach(fn=>fn(t));};
  advance(0);advance(5000);assert.equal(positions.at(-1).lat,2);
  cancel();assert.equal(frames.size,0);
  const stale=positions.length;advance(10000);assert.equal(positions.length,stale);
  const reduced=playJourney(plan,p=>positions.push(p),undefined,true);assert.equal(frames.size,0);assert.equal(positions.at(-1).lat,3);reduced();
  console.log('PASS: default scheduler preserves Window receiver for request/cancel, midpoint, reduced motion and cancellation');
}finally{await server.close();}
