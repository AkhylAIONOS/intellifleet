import assert from 'node:assert/strict';
import {JSDOM, VirtualConsole} from 'jsdom';
import {createServer} from 'vite';
const virtualConsole=new VirtualConsole();
virtualConsole.on('jsdomError',error=>{if(!error.message.includes('navigation'))throw error;});
const dom=new JSDOM('<!doctype html><html><body></body></html>',{url:'http://localhost/',virtualConsole});
for(const key of ['window','document','HTMLElement','Element','Node','navigator','localStorage','sessionStorage'])Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
HTMLElement.prototype.scrollIntoView=()=>{};
const React=await import('react');
const {render,act,fireEvent,cleanup}=await import('@testing-library/react');
const server=await createServer({
  define:{'import.meta.env.VITE_DEMO_ACCESS_ENABLED':JSON.stringify('true')},
  plugins:[{name:'auth-test-map-placeholder',enforce:'pre',transform(code,id){if(id.endsWith('/components/MapView.tsx'))return 'export const MapView = () => null;';}}],
  optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',
});
try {
  const {useAuthStore}=await server.ssrLoadModule('/src/store/authStore.ts');
  const {default:apiClient}=await server.ssrLoadModule('/src/api/client.ts');
  const {default:App}=await server.ssrLoadModule('/src/App.tsx');
  const {warehouseApi}=await server.ssrLoadModule('/src/api/warehouse.ts');warehouseApi.getInventory=async()=>({data:{inventory:[]}});
  const {warehousesApi}=await server.ssrLoadModule('/src/api/warehouses.ts');warehousesApi.getWarehouses=async()=>({warehouses:[]});
  const {vehiclesApi}=await server.ssrLoadModule('/src/api/vehicles.ts');vehiclesApi.getVehicles=async()=>({vehicles:[]});
  const {routesApi}=await server.ssrLoadModule('/src/api/routes.ts');routesApi.getRouteSession=async()=>({success:true,data:{routes:[]}});
  const {chatApi}=await server.ssrLoadModule('/src/api/chat.ts');chatApi.clearChat=async()=>{};
  const user={id:12,first_name:'UniFleet',last_name:'Demo',email:'demo@unifleet.local'};
  const tokenFor=seconds=>'header.'+Buffer.from(JSON.stringify({user_id:12,exp:Math.floor(Date.now()/1000)+seconds})).toString('base64url')+'.signature';
  const token=tokenFor(3600);
  let resolveRequest,calls=0;
  apiClient.defaults.adapter=config=>{
    calls++;assert.equal(config.url,'/auth/demo-access');assert.equal(config.method,'post');
    return new Promise(resolve=>{resolveRequest=()=>resolve({status:200,statusText:'OK',headers:{},config,data:{success:true,data:{token,user}}});});
  };
  for(const path of ['/','/login','/signup']) {
    useAuthStore.getState().clearAuth();window.history.replaceState({},'',path);
    const ui=render(React.createElement(App));
    assert.ok(ui.getByRole('heading',{name:'Welcome to UniFleet'}));
    assert.ok(ui.getByRole('button',{name:'Enter UniFleet'}));
    assert.equal(document.querySelectorAll('input,form,.auth-tabs,.auth-footer,.error-message').length,0);
    assert.equal(document.querySelector('.auth-right-panel .form-subtitle'),null);
    assert.equal(document.querySelector('.auth-form-wrapper').textContent.trim(),'Enter UniFleet');
    for(const text of ['Network Creation','Autonomous AI Route Agent','Visibility Twin','Advanced Analytics Dashboard'])assert.ok(ui.getByText(text));
    for(const text of ['40%','Cost Reduction','2×','Improved Planning','35%','Delay Improvements'])assert.ok(ui.getByText(text));
    assert.match(document.querySelector('.brand-title').textContent.replace(/\s+/g,' '),/AI-Powered Fleet\s*Intelligence/);
    assert.equal(document.querySelector('.brand-subtitle').textContent.trim(),'The autonomous logistics platform that thinks ahead — optimizing routes, predicting disruptions, and manages your entire fleet.');
    cleanup();
  }
  window.history.replaceState({},'','/login');let ui=render(React.createElement(App));
  await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Enter UniFleet'})));
  const pending=ui.getByRole('button',{name:'Entering UniFleet...'});assert.ok(pending.disabled);
  fireEvent.click(pending);assert.equal(calls,1);
  await act(async()=>resolveRequest());
  assert.equal(window.location.pathname,'/dashboard');assert.equal(localStorage.getItem('authToken'),token);
  assert.deepEqual(useAuthStore.getState().user,user);assert.ok(ui.getByRole('button',{name:/Logout/i}));
  cleanup();
  // Rehydrate the existing persisted store exactly as a new page load does.
  const persisted=localStorage.getItem('auth-storage');
  useAuthStore.setState({user:null,token:null,isAuthenticated:false});localStorage.setItem('auth-storage',persisted);
  await useAuthStore.persist.rehydrate();
  assert.equal(useAuthStore.getState().token,token);assert.equal(useAuthStore.getState().isAuthenticated,true);
  ui=render(React.createElement(App));await act(async()=>{});
  assert.equal(window.location.pathname,'/dashboard');
  await act(async()=>fireEvent.click(ui.getByRole('button',{name:/Logout/i})));
  assert.equal(localStorage.getItem('authToken'),null);assert.equal(useAuthStore.getState().user,null);
  assert.ok(ui.getByRole('button',{name:'Enter UniFleet'}));assert.equal(window.location.pathname,'/login');
  // A subsequent Enter returns to the protected dashboard with a token again.
  await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Enter UniFleet'})));
  await act(async()=>resolveRequest());assert.equal(window.location.pathname,'/dashboard');assert.equal(calls,2);
  cleanup();useAuthStore.getState().clearAuth();window.history.replaceState({},'','/');
  apiClient.defaults.adapter=async()=>{throw new Error('raw internal credentials or database error');};
  ui=render(React.createElement(App));await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Enter UniFleet'})));
  assert.equal(ui.queryByRole('alert'),null);
  assert.equal(ui.getByRole('button',{name:'Enter UniFleet'}).disabled,false);
  assert.doesNotMatch(document.body.textContent,/raw internal/);assert.equal(useAuthStore.getState().isAuthenticated,false);
  cleanup();
  localStorage.setItem('authToken',tokenFor(-10));localStorage.setItem('auth-storage',persisted);
  await useAuthStore.persist.rehydrate();assert.equal(useAuthStore.getState().isAuthenticated,false);
  window.history.replaceState({},'','/dashboard');ui=render(React.createElement(App));await act(async()=>{});
  assert.equal(window.location.pathname,'/login');assert.ok(ui.getByRole('button',{name:'Enter UniFleet'}));
  console.log('PASS: three demo landing routes, no auth inputs, loading/double-click, JWT storage, dashboard navigation, refresh, real logout, re-entry, safe errors and expiry');
} finally {cleanup();await server.close();dom.window.close();}
