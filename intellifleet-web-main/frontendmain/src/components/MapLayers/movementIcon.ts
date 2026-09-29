import L from 'leaflet';
const shapes: Record<string,string> = {
  SURFACE: '<path d="M3 8h17v15H3zM20 13h7l5 6v4H20z"/><circle cx="9" cy="25" r="4"/><circle cx="26" cy="25" r="4"/>',
  AIR: '<path d="M16 2l3 12 13 7v4l-13-4v9l4 3v2l-7-2-7 2v-2l4-3v-9L0 25v-4l13-7z"/>',
  RAIL: '<rect x="7" y="3" width="20" height="24" rx="5"/><path d="M10 11h14v7H10zM11 27l-5 7m17-7 5 7M9 31h16"/><circle cx="12" cy="23" r="2"/><circle cx="22" cy="23" r="2"/>',
};
const cache = new Map<string,L.DivIcon>();
export function movementIcon(mode: string, heading=0, selected=false, template=false) {
  const kind=mode==='AIR'?'AIR':mode==='RAIL'?'RAIL':'SURFACE';
  const rotation=Math.round((Number.isFinite(heading)?heading:0)/5)*5-(kind==='SURFACE'?90:0);
  const key=`${kind}-${rotation}-${selected}-${template}`;
  const cached=cache.get(key);if(cached)return cached;
  const icon=L.divIcon({className:'movement-icon',iconSize:[36,36],iconAnchor:[18,18],html:
    `<svg role="img" aria-label="${kind==='AIR'?'plane':kind==='RAIL'?'train':'truck'}" width="36" height="36" viewBox="-3 -3 42 42" style="opacity:${template ? 0.55 : 1};filter:drop-shadow(0 1px 2px #fff);transform:rotate(${rotation}deg)" fill="${selected?'#ff6600':'#2563eb'}" stroke="${selected?'#111':'#fff'}" stroke-width="2">${shapes[kind]}</svg>`});
  cache.set(key,icon);return icon;
}
