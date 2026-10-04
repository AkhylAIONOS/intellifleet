import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {createServer} from 'vite';
const dom=new JSDOM('<html><body></body></html>',{url:'http://localhost/'});
for(const key of ['window','document','HTMLElement','Element','Node','navigator','localStorage','sessionStorage'])Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
const React=await import('react');const {render,act,fireEvent,cleanup}=await import('@testing-library/react');
const server=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try{
 const {locationSuggestions}=await server.ssrLoadModule('/src/utils/networkLocations.ts');
 const {LocationInput}=await server.ssrLoadModule('/src/components/LocationInput.tsx');
 const locations=['Delhi','Mumbai','Bengaluru','Kolkata','Chennai','Chandigarh'];
 for(const [q,name] of [['D','Delhi'],['Mu','Mumbai'],['Ban','Bengaluru'],['Beng','Bengaluru'],['Kol','Kolkata'],['Bombay','Mumbai'],['Bangalore','Bengaluru'],['Mumabi','Mumbai'],['ennai','Chennai']])assert.ok(locationSuggestions(locations,q).includes(name),q);
 assert.equal(locationSuggestions(['Delhi'],'Bombay').length,0,'aliases cannot invent unavailable locations');
 assert.equal(locationSuggestions(locations,'CON-123').length,0);
 assert.ok(locationSuggestions(Array.from({length:500},(_,i)=>'Hub '+i),'Hub').length<=8);
 let value='';function Form(){const [v,set]=React.useState('');return React.createElement(LocationInput,{label:'Location',value:v,locations,onChange:x=>{value=x;set(x);}});}
 const ui=render(React.createElement(Form));const input=ui.getByRole('combobox');
 await act(async()=>fireEvent.change(input,{target:{value:'Ch'}}));
 assert.equal(ui.getAllByRole('option').length,2);
 await act(async()=>fireEvent.keyDown(input,{key:'ArrowDown'}));
 await act(async()=>fireEvent.keyDown(input,{key:'Enter'}));
 assert.ok(locations.includes(value));assert.equal(ui.queryByRole('listbox'),null);
 await act(async()=>fireEvent.change(input,{target:{value:'Bombay'}}));
 await act(async()=>fireEvent.click(ui.getByRole('option',{name:'Mumbai'})));
 assert.equal(value,'Mumbai');
 await act(async()=>fireEvent.change(input,{target:{value:'D'}}));
 await act(async()=>fireEvent.keyDown(input,{key:'Escape'}));assert.equal(ui.queryByRole('listbox'),null);
 console.log('PASS: loaded-network prefix/substring/typo/alias matching; canonical mouse/keyboard selection; Escape; capped local suggestions; exact IDs untouched');
}finally{cleanup();await server.close();dom.window.close();}
