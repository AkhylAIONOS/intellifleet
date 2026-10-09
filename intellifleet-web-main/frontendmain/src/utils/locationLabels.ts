import type {Warehouse} from '../types/api';
export function locationLabel(code:string,warehouses:Warehouse[]){return warehouses.find(w=>w.name===code)?.display_name||code;}
export function locationSearch(code:string,warehouses:Warehouse[]){const w=warehouses.find(w=>w.name===code);return [code,w?.display_name,...(w?.location_aliases||[])].filter(Boolean).join(' ');}
