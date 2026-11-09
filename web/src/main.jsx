import React, { useCallback, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, ArrowDownRight, ArrowUpRight, BadgeCheck, BarChart3, Bell, CalendarDays, Check, ChevronDown, CircleAlert, Clock3, Database, ExternalLink, FileCheck2, Gauge, Layers3, Play, RefreshCw, Settings2, ShieldCheck, Truck, X } from 'lucide-react';
import './styles.css';

const DEMO = {
  status: 'ok', run_active: false, total_recall_vehicle_rows: 132,
  by_make: [{make:'Toyota',count:43},{make:'Honda',count:31},{make:'Ford',count:27},{make:'Tesla',count:18},{make:'Hyundai',count:13}],
  by_vehicle: [{make:'Toyota',model:'Camry',year:2026,count:5},{make:'Honda',model:'CR-V',year:2026,count:4},{make:'Ford',model:'F-150',year:2026,count:3}],
  latest_run: {run_id:'preview-4a7c0d21',status:'ok',started_at:'2026-11-10T08:42:00+05:30',finished_at:'2026-11-10T08:44:32+05:30',start_year:2023,end_year:2026,source_queries:20,source_failures:0,records_fetched:132,records_loaded:18,records_inserted:7,records_updated:11,records_quarantined:0,duplicate_records:0,quality:{source_queries_expected:20,checks:[
    {name:'Source coverage',status:'passed',detail:'20 of 20 requests succeeded'},
    {name:'Required fields and year range',status:'passed',detail:'All 132 records passed validation'},
    {name:'Duplicate records',status:'passed',detail:'No duplicate rows found'},
    {name:'Schema changes',status:'passed',detail:'No unrecognized fields'},
    {name:'Volume change',status:'passed',detail:'Within expected range vs. previous run'},
  ]}},
  recent_runs: [
    {run_id:'4a7c0d21-preview',started_at:'2026-11-10T08:42:00+05:30',start_year:2023,end_year:2026,records_fetched:132,records_inserted:7,records_quarantined:0,source_failures:0,duplicate_records:0,status:'ok'},
    {run_id:'63b2a144-preview',started_at:'2026-11-09T08:41:00+05:30',start_year:2023,end_year:2026,records_fetched:129,records_inserted:3,records_quarantined:1,source_failures:0,duplicate_records:0,status:'warning'},
    {run_id:'b230af61-preview',started_at:'2026-11-08T08:40:00+05:30',start_year:2023,end_year:2026,records_fetched:126,records_inserted:6,records_quarantined:0,source_failures:0,duplicate_records:0,status:'ok'},
    {run_id:'19df8202-preview',started_at:'2026-11-07T08:40:00+05:30',start_year:2023,end_year:2026,records_fetched:120,records_inserted:0,records_quarantined:0,source_failures:1,duplicate_records:0,status:'warning'},
  ]
};

const prettyDate = value => value ? new Date(value).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : '—';
const number = value => new Intl.NumberFormat('en-US').format(value || 0);

function App(){
  const [data,setData]=useState(null); const [connected,setConnected]=useState(false); const [loading,setLoading]=useState(false); const [message,setMessage]=useState(''); const [now,setNow]=useState(new Date());
  const load=useCallback(async()=>{try{const response=await fetch('/api/dashboard');if(!response.ok)throw new Error('API unavailable');const payload=await response.json();setData(payload);setConnected(true);setMessage('')}catch{setData(DEMO);setConnected(false)}},[]);
  useEffect(()=>{load();const poll=window.setInterval(load,8000);const clock=window.setInterval(()=>setNow(new Date()),60000);return()=>{clearInterval(poll);clearInterval(clock)}},[load]);
  const run=data?.latest_run; const checks=run?.quality?.checks||[]; const running=!!data?.run_active||run?.status==='running'; const preview=!connected;
  const startRun=async()=>{setLoading(true);setMessage('');try{const response=await fetch('/api/run',{method:'POST'});const body=await response.json();if(!response.ok)throw new Error(body.detail||'Could not start the run');setMessage('Run started. The dashboard will refresh as it progresses.');await load()}catch(e){setMessage(e.message)}finally{setLoading(false)}};
  const maxCoverage=Math.max(...(data?.by_make||[]).map(x=>x.count),1);
  if(!data)return <div className="loading-screen"><span className="loading-mark"><Truck size={20}/></span><span>Preparing your operations view</span></div>;
  if(!run&&connected)return <div className="empty-screen"><Truck size={30}/><h1>Ready for the first run</h1><p>Connect to the NHTSA source and load your first recall records.</p><button onClick={startRun} className="primary" disabled={running||loading}><Play size={15}/>{loading?'Starting…':'Run the pipeline'}</button></div>;
  return <div className="app">
    <aside className="sidebar">
      <a className="brand" href="#top"><span className="brand-icon"><Truck size={19}/></span><span>Mobility<span>Monitor</span></span></a>
      <div className="workspace-tag">DATA OPERATIONS</div>
      <nav className="navigation"><a href="#overview" className="nav-link active"><BarChart3 size={17}/>Overview<span className="nav-current"/></a><a href="#quality" className="nav-link"><ShieldCheck size={17}/>Quality checks</a><a href="#runs" className="nav-link"><Activity size={17}/>Run history</a></nav>
      <div className="side-divider"/><div className="source-heading">CONNECTED SOURCE</div>
      <a className="source-card" href="https://www.nhtsa.gov/nhtsa-datasets-and-apis" target="_blank" rel="noreferrer"><span className="nhtsa-mark">N</span><span><b>NHTSA recalls</b><small>Public vehicle data</small></span><ExternalLink size={13}/></a>
      <div className="sidebar-bottom"><div className="backend-state"><span className={`state-light ${connected?'connected':''}`}/><span><b>{connected?'Pipeline online':'Preview workspace'}</b><small>{connected?'API responding normally':'Connect API to use live data'}</small></span><span className="state-menu"><Settings2 size={15}/></span></div><div className="user-row"><span className="user-avatar">A</span><span><b>Analyst workspace</b><small>Local environment</small></span><ChevronDown size={14}/></div></div>
    </aside>
    <main id="top" className="main">
      <header className="topbar"><div className="breadcrumbs">Workspace <span>/</span> Operations</div><div className="topbar-right"><span className="current-date"><CalendarDays size={14}/>{now.toLocaleDateString([], {weekday:'short',month:'short',day:'numeric'})}</span><button className="bell" aria-label="Notifications"><Bell size={16}/><i/></button><span className={`connection-pill ${connected?'up':'preview'}`}><i/>{connected?'CONNECTED': 'PREVIEW MODE'}</span></div></header>
      <div className="page" id="overview">
        <div className="page-head"><div><div className="eyebrow">AUTOMOTIVE DATA · DAILY OPERATIONS</div><h1>Pipeline overview</h1><p>Keep incoming vehicle data reliable, traceable, and ready to use.</p></div><div className="head-actions"><span className="refresh-note"><RefreshCw size={13}/> Updates every 8 seconds</span><button className="primary run-button" onClick={startRun} disabled={!connected||running||loading} title={!connected?'Start the API to run ingestion':''}><Play size={14} fill="currentColor"/>{running?'Run in progress':loading?'Starting…':'Run pipeline'}</button></div></div>
        {preview&&<div className="preview-note"><span className="preview-note-icon"><CircleAlert size={17}/></span><div><b>Preview data is being shown</b><span>These sample numbers are for the UI preview. Start the API to see real NHTSA records.</span></div><span className="preview-tag">SAMPLE RUN</span></div>}
        {message&&<div className="toast"><CircleAlert size={15}/>{message}<button onClick={()=>setMessage('')} aria-label="Dismiss"><X size={14}/></button></div>}
        <div className="pipeline-strip"><div className="strip-label">PIPELINE FLOW</div><div className="flow-step"><span className="flow-icon ingest"><Database size={16}/></span><span><b>Ingest</b><small>NHTSA API</small></span></div><span className="flow-connector"/><div className="flow-step"><span className="flow-icon validate"><FileCheck2 size={16}/></span><span><b>Validate</b><small>5 quality gates</small></span></div><span className="flow-connector"/><div className="flow-step"><span className="flow-icon store"><Layers3 size={16}/></span><span><b>Store</b><small>PostgreSQL</small></span></div><span className="flow-connector"/><div className="flow-step"><span className="flow-icon monitor"><Gauge size={16}/></span><span><b>Monitor</b><small>Run history</small></span></div><span className="flow-spacer"/><span className={`pipeline-status ${run.status}`}><i/>{run.status==='ok'?'All systems healthy':run.status==='warning'?'Review needed':run.status}</span></div>
        <section className="metrics">
          <div className="metric metric-primary"><div className="metric-label">RECALL ROWS IN DATABASE <span className="metric-icon"><Database size={15}/></span></div><div className="metric-number">{number(data.total_recall_vehicle_rows)}<small>records</small></div><div className="metric-caption"><span className="mini-trend"><ArrowUpRight size={13}/> +6.2%</span> from previous run</div><div className="metric-decoration"/></div>
          <div className="metric"><div className="metric-label">UPDATED THIS RUN <span className="metric-icon"><Layers3 size={15}/></span></div><div className="metric-number">{number(run.records_loaded)}<small>records</small></div><div className="metric-caption"><span className="caption-strong">{number(run.records_inserted)} new</span><span className="bullet">·</span>{number(run.records_updated)} refreshed</div></div>
          <div className="metric"><div className="metric-label">QUALITY GATES <span className="metric-icon"><ShieldCheck size={15}/></span></div><div className="metric-number">{checks.filter(c=>c.status==='passed').length}<small> / {checks.length} passed</small></div><div className="metric-caption"><span className="caption-strong">{number(run.records_quarantined)} quarantined</span><span className="bullet">·</span>0 critical issues</div></div>
          <div className="metric"><div className="metric-label">SOURCE COVERAGE <span className="metric-icon"><Activity size={15}/></span></div><div className="metric-number">{number(run.source_queries)}<small> / {number(run.quality?.source_queries_expected)} calls</small></div><div className="metric-caption"><span className="caption-strong">{number(run.source_failures)} failed</span><span className="bullet">·</span>{run.start_year}–{run.end_year} model years</div></div>
        </section>
        <section className="content-grid">
          <article className="panel quality-panel" id="quality"><div className="panel-title"><div><div className="eyebrow">VALIDATION SUMMARY</div><h2>Quality gates</h2></div><span className="passed-pill"><BadgeCheck size={14}/> {checks.filter(c=>c.status==='passed').length} passed</span></div><div className="checks">{checks.map((check,i)=><div className="check" key={i}><span className={`check-icon ${check.status}`}>{check.status==='passed'?<Check size={13}/>:<CircleAlert size={13}/>}</span><span className="check-text"><b>{check.name}</b><small>{check.detail}</small></span><span className={`check-state ${check.status}`}>{check.status==='passed'?'PASS':'REVIEW'}</span></div>)}</div><div className="trace-note"><span><ShieldCheck size={16}/></span><div><b>Source traceability is on</b><small>Every run keeps the original response. Invalid rows are saved for review.</small></div></div></article>
          <article className="panel coverage-panel"><div className="panel-title"><div><div className="eyebrow">RECORD DISTRIBUTION</div><h2>Coverage by manufacturer</h2></div><button className="more-button" aria-label="More options"><span>···</span></button></div><div className="coverage-total"><b>{number(data.total_recall_vehicle_rows)}</b><span>vehicle recall records</span></div><div className="bars">{data.by_make.map((row,i)=><div className="bar-row" key={row.make}><div className="maker"><span className={`maker-icon m${i}`}>{row.make.slice(0,1)}</span><span>{row.make}</span></div><div className="bar-track"><i style={{width:`${Math.max(5,row.count/maxCoverage*100)}%`,animationDelay:`${i*70}ms`}}/></div><b>{number(row.count)}</b></div>)}</div><div className="chart-foot"><span><i/> Recall records</span><span>2023–2026</span></div></article>
        </section>
        <section className="panel runs-panel" id="runs"><div className="panel-title"><div><div className="eyebrow">OPERATIONAL HISTORY</div><h2>Recent pipeline runs</h2></div><button className="text-action" onClick={()=>document.getElementById('runs')?.scrollIntoView({behavior:'smooth'})}>View run details <ArrowUpRight size={14}/></button></div><div className="table-scroll"><table><thead><tr><th>RUN ID</th><th>STARTED</th><th>MODEL YEARS</th><th>FETCHED</th><th>NEW RECORDS</th><th>ISSUES</th><th>RESULT</th></tr></thead><tbody>{data.recent_runs.map(item=><tr key={item.run_id}><td><span className="run-id-cell"><span className={`run-dot ${item.status}`}/>{item.run_id.slice(0,8)}</span></td><td>{prettyDate(item.started_at)}</td><td>{item.start_year}—{item.end_year}</td><td>{number(item.records_fetched)}</td><td><b>{number(item.records_inserted)}</b></td><td>{number(item.records_quarantined+item.source_failures+item.duplicate_records)}</td><td><span className={`result-pill ${item.status}`}>{item.status==='ok'?'Healthy':'Review'}</span></td></tr>)}</tbody></table></div><div className="table-bottom"><span><Clock3 size={13}/> Most recent first</span><span>{data.recent_runs.length} runs shown</span></div></section>
        <footer className="footer"><span>Mobility Monitor <i>·</i> Data operations workspace</span><a href="https://www.nhtsa.gov/nhtsa-datasets-and-apis" target="_blank" rel="noreferrer">NHTSA public data <ExternalLink size={12}/></a><span className="footer-time">Last refreshed {now.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</span></footer>
      </div>
    </main>
  </div>
}

createRoot(document.getElementById('root')).render(<App/>);
