import {useId,useMemo,useState} from 'react';
import {useAppStore} from '../store/appStore';
import {locationLabel} from '../utils/locationLabels';
import {locationSuggestions} from '../utils/networkLocations';
import './LocationInput.css';

export function LocationInput({value,onChange,locations,placeholder,label,disabled=false}:{value:string;onChange:(value:string)=>void;locations?:string[];placeholder?:string;label?:string;disabled?:boolean}){
 const warehouses=useAppStore(s=>s.warehouses),routes=useAppStore(s=>s.activeRoutes);
 const available=useMemo(()=>locations??[...warehouses.map(w=>w.name),...Object.values(routes).filter(r=>!r.routeData?.planning).flatMap(r=>[r.source,r.destination])].filter((v):v is string=>typeof v==='string'&&!!v),[locations,warehouses,routes]);
 const options=useMemo(()=>{const aliases=available.flatMap(code=>{const w=warehouses.find(w=>w.name===code);return [code,w?.display_name,...(w?.location_aliases||[])].filter((v):v is string=>!!v).map(alias=>({code,alias}));});const matches=locationSuggestions(aliases.map(v=>v.alias),available.includes(value)?'':value,20);return [...new Set(matches.flatMap(alias=>aliases.filter(v=>v.alias===alias).map(v=>v.code)))].slice(0,8);},[available,value,warehouses]);
 const [open,setOpen]=useState(false),[active,setActive]=useState(-1);const id=useId();
 const pick=(name:string)=>{onChange(name);setOpen(false);setActive(-1);};
 return <span className="location-input"><input role="combobox" aria-label={label} aria-autocomplete="list" aria-expanded={open&&options.length>0} aria-controls={id} aria-activedescendant={open&&active>=0?`${id}-${active}`:undefined} autoComplete="off" disabled={disabled} value={locationLabel(value,warehouses)} placeholder={placeholder}
  onFocus={()=>setOpen(true)} onBlur={()=>setOpen(false)} onChange={e=>{onChange(e.target.value);setActive(-1);setOpen(true);}}
  onKeyDown={e=>{if(e.key==='Escape'){setOpen(false);setActive(-1);}else if((e.key==='ArrowDown'||e.key==='ArrowUp')&&options.length){e.preventDefault();setOpen(true);setActive(i=>i<0?(e.key==='ArrowDown'?0:options.length-1):(i+(e.key==='ArrowDown'?1:-1)+options.length)%options.length);}else if(e.key==='Enter'&&open&&options.length){e.preventDefault();pick(options[Math.max(0,active)]);}}}/>
  {open&&options.length>0&&<span role="listbox" id={id} className="location-options">{options.map((name,i)=><span role="option" id={`${id}-${i}`} key={name} aria-selected={active===i} onMouseDown={e=>e.preventDefault()} onClick={()=>pick(name)}>{locationLabel(name,warehouses)}</span>)}</span>}
 </span>;
}
