/* Connected-agent AsyncFunction body: (tools, options).
 * Source-first discovery is open-world. An agent reviews the extracted company/
 * event/date/domain manifest before ICP qualification and paid contact enrichment.
 * This is an agent-assisted live runner, not a deployed unattended service.
 */
const root=options.root||'/Volumes/SeagateSSD/Projects/gtm-engineering/signoz';
const base='results/signal_first_v3/';
const stage=options.stage||'discover';
const quote=s=>"'"+s.replace(/'/g,"'\\''")+"'";
async function shell(cmd){const r=await tools.exec_command({cmd,workdir:root,max_output_tokens:18000});if(r.exit_code!==0)throw Error(r.output);return r.output;}
async function read(p){return JSON.parse(await shell('cat '+quote(p)));}
async function save(p,r){await tools.apply_patch('*** Begin Patch\n*** Add File: '+root+'/'+p+'\n+'+JSON.stringify(r,null,2).split('\n').join('\n+')+'\n*** End Patch');}
const unpack=r=>r.structuredContent||JSON.parse(r.content.find(c=>c.type==='text').text);
const run={stage,started_at:new Date().toISOString(),errors:[],outreach_sent:0};
if(stage==='discover'){
 const queries=options.queries||[
  'ecommerce retailer new fulfilment centre 2026 Europe United States',
  'fashion beauty brand international ecommerce expansion 2026',
  'marque ecommerce nouveau entrepot logistique 2026 France',
  'ecommerce nuovo polo logistico 2026 Italia',
  'online retailer Logistikzentrum Expansion 2026 Deutschland',
  'ecommerce nuevo centro logistico 2026 España'
 ];
 if(!tools.mcp__codex_apps__search_service_web_run)throw Error('Connected web search is unavailable.');
 const stamp=run.started_at.replace(/[^0-9]/g,'').slice(0,14);run.receipts=[];
 for(let i=0;i<queries.length;i++){
  const result=await tools.mcp__codex_apps__search_service_web_run({system2_search_query:[{q:queries[i]}],response_length:'long'});
  const path=base+'raw/refresh-'+stamp+'-'+i+'.json';await save(path,{query:queries[i],retrieved_at:run.started_at,result});run.receipts.push(path);
  if(options.onProgress)options.onProgress({stage,completed:i+1,total:queries.length});
 }
 run.next='Review these source receipts into signal_candidates.json with attributable company, canonical domain, event, date and source ID. Do not seed discovery from the old company roster. Then resolve company profiles, build, and run enrich.';
}else if(stage==='enrich'){
 await shell('python3 src/pipeline.py build');
 const accounts=await read(base+'selected_accounts.json');
 if(accounts.length!==50||accounts.some(r=>r.qualification!=='qualified'||r.signal_status!=='current'||!r.source_id||!r.source_url))throw Error('A reviewed, current, ICP-qualified source manifest is required.');
 const requested=[];
 // Company qualification precedes person searches. Sequential calls respect
 // the observed workspace concurrency limit and preserve page-specific task IDs.
 for(let i=0;i<accounts.length;i+=10){
  let r=await tools.mcp__codex_apps__clay_search_contacts({companyIdentifiers:accounts.slice(i,i+10).map(a=>a.domain),dslQuery:'select from people where experiences.any(is_current = true and seniority in ("C-suite","VP","Director","Head") and job_title contains ("logistics","supply","ecommerce","e-commerce","operations","COO","digital","logistique","logistica") and not job_title contains ("HR","Human Resources","Talent","Real Estate")) limit 2 by clay_company_id limit 20'});
  if(r.isError){run.errors.push({stage:'contacts',offset:i,result:r});continue;}
  let p=unpack(r),page=0;
  while(true){await save(base+'raw/contacts-refresh-'+i+'-'+page+'.json',r);requested.push({taskId:p.taskId,contacts:p.contacts||[]});if(!p.hasMore)break;r=await tools.mcp__codex_apps__clay_load_more_search_results({taskId:p.taskId});p=unpack(r);page++;}
 }
 await shell('python3 src/pipeline.py build');
 const allowed=await read(base+'selected_accounts.json');
 const primary=new Set(allowed.map(r=>r.primary_contact?.entityId).filter(Boolean));
 for(const task of requested){
  const ids=task.contacts.filter(c=>primary.has(c.entityId)).map(c=>c.entityId);if(!ids.length)continue;
  await tools.mcp__codex_apps__clay_add_contact_data_points({taskId:task.taskId,entityIds:ids,dataPoints:[{type:'Email'}]});
  const context=await tools.mcp__codex_apps__clay_get_task_context({taskId:task.taskId});await save(base+'raw/email-context-'+task.taskId+'.json',context);
 }
 await shell('python3 src/pipeline.py build');run.summary=await read(base+'summary.json');run.pending='Inspect async email statuses and poll get_task_context for pending tasks; preserve each context. Review employer/title conflicts before accepting new records.';
}else if(stage==='build'){
 await shell('python3 src/pipeline.py build');run.summary=await read(base+'summary.json');
}else throw Error('Unknown stage; choose discover, enrich or build.');
await save(base+'live_run.json',run);return run;
