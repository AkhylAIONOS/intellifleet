import {useId,useMemo,useState} from 'react';
import {useAppStore} from '../store/appStore';
import {locationSuggestions} from '../utils/networkLocations';
import './LocationInput.css';

export function LocationInput({value,onChange,locations,placeholder,label}:{value:string;onChange:(value:string)=>void;locations?:string[];placeholder?:string;label?:string}){
 const warehouses=useAppStore(s=>s.warehouses),routes=useAppStore(s=>s.activeRoutes);
 const available=useMemo(()=>locations??[...warehouses.map(w=>w.name),...Object.values(routes).filter(r=>!r.routeData?.planning).flatMap(r=>[r.source,r.destination])].filter((v):v is string=>typeof v==='string'&&!!v),[locations,warehouses,routes]);
 const options=useMemo(()=>locationSuggestions(available,value),[available,value]);
 const [open,setOpen]=useState(false),[active,setActive]=useState(-1);const id=useId();
 const pick=(name:string)=>{onChange(name);setOpen(false);setActive(-1);};
 return <span className="location-input"><input role="combobox" aria-label={label} aria-autocomplete="list" aria-expanded={open&&options.length>0} aria-controls={id} aria-activedescendant={open&&active>=0?`${id}-${active}`:undefined} autoComplete="off" value={value} placeholder={placeholder}
  onFocus={()=>setOpen(true)} onBlur={()=>setOpen(false)} onChange={e=>{onChange(e.target.value);setActive(-1);setOpen(true);}}
  onKeyDown={e=>{if(e.key==='Escape'){setOpen(false);setActive(-1);}else if((e.key==='ArrowDown'||e.key==='ArrowUp')&&options.length){e.preventDefault();setOpen(true);setActive(i=>i<0?(e.key==='ArrowDown'?0:options.length-1):(i+(e.key==='ArrowDown'?1:-1)+options.length)%options.length);}else if(e.key==='Enter'&&open&&options.length){e.preventDefault();pick(options[Math.max(0,active)]);}}}/>
  {open&&options.length>0&&<span role="listbox" id={id} className="location-options">{options.map((name,i)=><span role="option" id={`${id}-${i}`} key={name} aria-selected={active===i} onMouseDown={e=>e.preventDefault()} onClick={()=>pick(name)}>{name}</span>)}</span>}
 </span>;
}
