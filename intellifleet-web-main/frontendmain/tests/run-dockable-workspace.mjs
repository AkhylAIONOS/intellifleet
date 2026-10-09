import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';import {createServer} from 'vite';
const dom=new JSDOM('<html><body></body></html>',{url:'http://localhost/'});
for(const key of ['window','document','HTMLElement','Element','Node','navigator','localStorage'])Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
const React=await import('react');const {render,fireEvent,act,cleanup}=await import('@testing-library/react');const server=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try{
 const {DockableWorkspace,boundFloating,readLayout}=await server.ssrLoadModule('/src/components/DockableWorkspace.tsx');
 const {ROUTE_PALETTE}=await server.ssrLoadModule('/src/utils/routePalette.ts');assert.equal(new Set(ROUTE_PALETTE).size,4);
 const rect=boundFloating({x:-20,y:900,width:9000,height:9000},900,600);assert.deepEqual(rect,{x:0,y:0,width:900,height:600});
 localStorage.setItem('broken','{oops');assert.equal(readLayout('broken').dockPosition,'right');
 let mounts=0,unmounts=0;
 const Map=()=>{React.useEffect(()=>{mounts++;return()=>unmounts++;},[]);return React.createElement('div',{'data-testid':'map'},'map');};
 const ui=render(React.createElement(DockableWorkspace,{primaryContent:'content',mapContent:React.createElement(Map),storageKey:'test-dock',label:'test'}));
 const workspace=ui.container.querySelector('.dockable-workspace');
 for(const position of ['left','top','bottom','floating','right']){await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Dock '+position,hidden:true})));assert.equal(workspace.dataset.dockPosition,position);assert.equal(readLayout('test-dock').dockPosition,position);assert.equal(mounts,1);assert.equal(unmounts,0);}
 await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Dock left',hidden:true})));
 await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Expand map'})));assert.equal(workspace.dataset.maximized,'true');assert.equal(readLayout('test-dock').previousLayout.dockPosition,'left');
 await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Restore map'})));assert.equal(workspace.dataset.maximized,'false');assert.equal(workspace.dataset.dockPosition,'left');assert.equal(mounts,1);
 await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Reset layout',hidden:true})));assert.equal(workspace.dataset.dockPosition,'right');assert.equal(readLayout('test-dock').splitRatio,50);
 cleanup();assert.equal(unmounts,1);
 console.log('PASS: five dock positions, persistence, malformed storage, floating bounds, maximize/restore/reset, stable map lifetime and unique route palette');
}finally{cleanup();await server.close();dom.window.close();}
