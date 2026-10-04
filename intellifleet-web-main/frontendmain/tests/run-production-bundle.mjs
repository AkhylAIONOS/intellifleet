// Optional post-build check: exercises emitted ESM without claiming browser QA.
import assert from 'node:assert/strict';
import {readdir} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {JSDOM} from 'jsdom';
let assets;
try{assets=await readdir(resolve('dist/assets'));}catch{console.log('SKIP: build first to validate emitted production modules');process.exit(0);}
const entry=assets.find(name=>/^index-.*\.js$/.test(name));
assert.ok(entry,'production entry exists');
const dom=new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>',{url:'http://localhost/'});
for(const key of ['window','document','HTMLElement','Element','Node','navigator','localStorage','sessionStorage','MutationObserver'])Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
HTMLElement.prototype.scrollIntoView=()=>{};
try{
 await import(pathToFileURL(resolve('dist/assets',entry)).href);
 for(let i=0;i<100&&!document.querySelector('.brand-title');i++)await new Promise(done=>setTimeout(done,10));
 assert.match(document.body.textContent,/UniFleet/);
 assert.ok(document.querySelector('.brand-title'),'split production modules initialize landing UI');
 assert.ok(document.querySelector('button'),'landing action renders');
 console.log('PASS: emitted production ESM and vendor chunk initialize landing DOM without module-cycle errors');
}finally{dom.window.close();}
// The emitted app owns long-lived query timers; this dedicated process ends here.
process.exit(0);
