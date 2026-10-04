const key=(value:string)=>value.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]/g,'');
const aliases:Record<string,string[]>= {mumbai:['bombay'],bengaluru:['bangalore','bang'],kolkata:['calcutta'],chennai:['madras'],delhi:['new delhi']};
function distance(a:string,b:string){
 let previous=Array.from({length:b.length+1},(_,i)=>i);
 for(let i=0;i<a.length;i++){const current=[i+1];for(let j=0;j<b.length;j++)current[j+1]=Math.min(current[j]+1,previous[j+1]+1,previous[j]+(a[i]===b[j]?0:1));previous=current;}
 return previous[b.length];
}
export function locationSuggestions(locations:string[],query:string,limit=8):string[]{
 const q=key(query);if(!q)return [];
 return [...new Set(locations.filter(Boolean))].map(name=>{
  const values=[key(name),...(aliases[key(name)]||[]).map(key)];
  const score=Math.min(...values.map(v=>v===q?0:v.startsWith(q)?1:v.includes(q)?2:q.length>=3&&distance(q,v.slice(0,Math.max(q.length,Math.min(v.length,q.length+1))))<=1?3:q.length>=4&&distance(q,v)<=2?4:99));
  return {name,score};
 }).filter(x=>x.score<99).sort((a,b)=>a.score-b.score||a.name.localeCompare(b.name)).slice(0,limit).map(x=>x.name);
}
