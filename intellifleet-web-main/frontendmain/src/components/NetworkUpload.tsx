import { useState } from 'react';
import apiClient from '../api/client';
import { useAppStore } from '../store/appStore';

type UploadFiles = { warehouse?: File; vehicle?: File; routes?: File };

export const formatUploadError = (error: any): string => {
  const status = error.response?.status;
  if (status === 401) return 'Network upload failed: authentication required. Please sign in again.';
  if (status === 403) return 'Network upload failed: you do not have permission to upload.';
  if (status >= 500) return 'Network upload failed: the server could not complete the import. Please try again.';
  if (!error.response) return 'Network upload failed: unable to reach the API. Check that the backend is running and allows this frontend origin.';
  const detail = error.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((item: any) => `${item.loc?.at(-1) || 'request'}: ${item.msg || 'Invalid value'}`).join('\n');
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') return Object.entries(detail).map(([key, value]) => `${key}: ${String(value)}`).join('\n');
  return error.message || 'Network upload failed';
};

export const NetworkUpload = () => {
  const warehouses=useAppStore(state=>state.warehouses); const vehicles=useAppStore(state=>state.vehicles); const activeRoutes=useAppStore(state=>state.activeRoutes);
  const [files,setFiles]=useState<UploadFiles>({});
  const [result,setResult]=useState<any>(()=>{const saved=sessionStorage.getItem('networkUploadResult'); if(saved) sessionStorage.removeItem('networkUploadResult'); return saved?JSON.parse(saved):undefined});
  const [busy,setBusy]=useState(false);
  const choose=(key:keyof UploadFiles,file?:File)=>setFiles(current=>({...current,[key]:file}));
  const upload=async()=>{if(!files.warehouse||!files.vehicle||!files.routes)return; const formData=new FormData(); formData.append('warehouse_csv',files.warehouse); formData.append('vehicle_csv',files.vehicle); formData.append('routes_csv',files.routes); setBusy(true); setResult(undefined);
    try{const data=(await apiClient.post('/upload-network',formData,{timeout:120000,headers:{'Content-Type':undefined}})).data; sessionStorage.setItem('networkUploadResult',JSON.stringify(data)); window.location.reload();}catch(e:any){setResult({error:formatUploadError(e),status:e.response?.status}); setBusy(false)}};
  const activeCount=Object.values(activeRoutes).filter(route=>route.isActive!==false&&!route.routeData?.planning).length;
  const uploadCounts=result?.counts||result?.data?.counts||result;
  return <div className="network-tools">
    <section className="network-upload-card"><div className="section-title"><span>Upload Network Data</span><small>3 CSV files · atomic import</small></div><div className="network-upload-fields">
      {(['warehouse','vehicle','routes'] as const).map(key=><label key={key}><span>{key==='warehouse'?'Warehouse':key==='vehicle'?'Vehicle':'Routes'} CSV</span><span className="file-picker"><b>{files[key]?.name||'Choose file'}</b><input type="file" accept=".csv,text/csv" onChange={e=>choose(key,e.target.files?.[0])}/></span></label>)}
      <button disabled={busy||!files.warehouse||!files.vehicle||!files.routes} onClick={upload}>{busy?'Processing…':'Upload & Process'}</button>
    </div>{result?.error&&<div role="alert" className="upload-error"><strong>Upload failed{result.status?` (HTTP ${result.status})`:''}</strong><span>{result.error}</span></div>}{result?.success&&<div className="upload-success"><strong>{result.rows!=null?'Schedules ready':'Network ready'}</strong><span>{result.rows!=null?`${result.rows} synthetic schedules imported`:uploadCounts.processing_ms!=null?`${uploadCounts.processing_ms} ms`: 'Upload processed successfully'}</span></div>}</section>
    <section className="network-upload-card"><strong>Synthetic V2 demo data</strong><p>{['warehouse','vehicle','routes','schedules'].map(name=><a key={name} href={`/synthetic_v2/${name}.csv`} download style={{marginRight:12}}>{name}.csv</a>)}</p>
    <label>Import separate synthetic schedule CSV<input type="file" accept=".csv" onChange={async e=>{const file=e.target.files?.[0];if(!file)return;const form=new FormData();form.append('file',file);try{const r=await apiClient.post('/operations/schedules/import',form,{headers:{'Content-Type':undefined}});setResult(r.data);}catch(error){setResult({error:formatUploadError(error)});}}}/></label><small>Schedules remain separate from network fleet and FedEx workbook provenance. Schedule uploads are ephemeral.</small></section>
    <section className="network-summary"><div className="section-title"><span>Network Summary</span><i></i></div><dl><div><dt>Warehouses</dt><dd>{warehouses.length}</dd></div><div><dt>Vehicles</dt><dd>{vehicles.length}</dd></div><div><dt>Routes</dt><dd>{activeCount}</dd></div></dl></section>
  </div>;
};
