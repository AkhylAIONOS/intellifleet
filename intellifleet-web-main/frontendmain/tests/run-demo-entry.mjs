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
  const user={id:12,name:'Test User',first_name:'Test',last_name:'User',email:'test@example.com'};
  const token='header.'+Buffer.from(JSON.stringify({user_id:12,exp:Math.floor(Date.now()/1000)+3600})).toString('base64url')+'.signature';
  let calls=0,admin=false;
  apiClient.defaults.adapter=async config=>{
    if(config.url==='/operations/control-tower/runs')return {status:200,statusText:'OK',headers:{},config,data:{runs:[],total:0}};
    if(config.url==='/operations/movements')return {status:200,statusText:'OK',headers:{},config,data:{movements:[]}};
    if(config.url==='/auth/users'){
      if(!admin)throw {response:{status:403}};
      return {status:200,statusText:'OK',headers:{},config,data:{users:[{name:'Test User',email:'test@example.com',first_login_at:'2030-01-01',last_login_at:'2030-01-02',login_count:2},{name:'Second User',email:'second@example.com',first_login_at:'2030-01-02',last_login_at:'2030-01-02',login_count:1}]}};
    }
    if(config.url==='/client-network')return {status:200,statusText:'OK',headers:{},config,data:{summary:{client_services:38,client_nodes:34,generated_resources:40,simulated_shipments:320},routes:[],vehicles:[]}};
    calls++;assert.equal(config.url,'/auth/demo-access');
    assert.deepEqual(JSON.parse(config.data),{name:'Test User',email:'test@example.com'});
    return {status:200,statusText:'OK',headers:{},config,data:{success:true,data:{token,user}}};
  };
  async function login(ui){
    await act(async()=>{
      fireEvent.change(ui.getByLabelText('Name'),{target:{value:'Test User'}});
      fireEvent.change(ui.getByLabelText('Email'),{target:{value:'TEST@example.com'}});
      fireEvent.submit(ui.getByRole('button',{name:'Continue to UniFleet'}).closest('form'));
    });
  }
  window.history.replaceState({},'','/internal/users');let ui=render(React.createElement(App));
  assert.equal(window.location.pathname,'/login');
  assert.ok(ui.getByRole('heading',{name:'Welcome to UniFleet'}));
  await login(ui);
  assert.equal(window.location.pathname,'/dashboard');assert.equal(localStorage.getItem('authToken'),token);
  assert.ok(ui.getByText(/Test User/));assert.ok(ui.getByText('test@example.com'));
  assert.ok(ui.getByRole('button',{name:'Planning',exact:true}));assert.ok(ui.getByRole('button',{name:'Live Operations',exact:true}));
  assert.equal(document.querySelector('a[href="/internal/users"]'),null);
  cleanup();
  const persisted=localStorage.getItem('auth-storage');useAuthStore.setState({user:null,token:null,isAuthenticated:false});localStorage.setItem('auth-storage',persisted);
  await useAuthStore.persist.rehydrate();assert.equal(useAuthStore.getState().isAuthenticated,true);
  ui=render(React.createElement(App));await act(async()=>{});
  await act(async()=>fireEvent.click(ui.getByRole('button',{name:'Logout',exact:true})));
  assert.equal(localStorage.getItem('authToken'),null);assert.equal(window.location.pathname,'/login');
  await login(ui);assert.equal(calls,2);assert.equal(window.location.pathname,'/dashboard');cleanup();
  window.history.replaceState({},'','/internal/users');ui=render(React.createElement(App));await act(async()=>{});
  assert.ok(ui.getByRole('alert'));assert.match(ui.getByRole('alert').textContent,/Unauthorized/);
  assert.equal(ui.queryByRole('table'),null);cleanup();
  admin=true;ui=render(React.createElement(App));await act(async()=>{});
  assert.ok(ui.getByRole('table'));assert.ok(ui.getByText('second@example.com'));assert.ok(ui.getByRole('columnheader',{name:'Login Count'}));cleanup();
  useAuthStore.getState().clearAuth();window.history.replaceState({},'','/login');
  apiClient.defaults.adapter=async()=>{throw new Error('private internal database error');};
  ui=render(React.createElement(App));await login(ui);
  assert.ok(ui.getByRole('alert'));assert.doesNotMatch(ui.getByRole('alert').textContent,/private internal/);
  console.log('PASS: name/email login, normalized identity, header display, dashboard/navigation, refresh, logout/relogin, protected hidden route, 403 handling, admin list, clean errors');
} finally {cleanup();await server.close();dom.window.close();}
