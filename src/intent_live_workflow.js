/* Connected-agent AsyncFunction body receiving (tools, options).
 * Live search -> fetched evidence -> strict intent gate -> eligible contacts.
 * Analyst reviews never become qualified merely because a search returned a URL.
 */
const root=options.root||'/Volumes/SeagateSSD/Projects/gtm-engineering/signoz';
const raw='results/intent_v2/raw/';
async function shell(cmd){const r=await tools.exec_command({cmd,workdir:root,max_output_tokens:18000});if(r.exit_code!==0)throw new Error(r.output);return r.output;}
async function read(path){return JSON.parse(await shell('cat '+path));}
async function save(path,data){const s=JSON.stringify(data,null,2);await tools.apply_patch('*** Begin Patch\n*** Add File: '+root+'/'+path+'\n+'+s.split('\n').join('\n+')+'\n*** End Patch');}
async function web(args){
  if(tools.mcp__codex_apps__search_service_web_run)return await tools.mcp__codex_apps__search_service_web_run(args);
  if(tools.web__run){const a={...args};if(a.system2_search_query){a.search_query=a.system2_search_query;delete a.system2_search_query;}const r=await tools.web__run(a);return typeof r==='string'?{content:[{type:'text',text:r}]}:r;}
  throw new Error('Connected public web search tool is unavailable. No mock data will be substituted.');
}
const now=(await tools.clock__curr_time({})).current_time;
const contract=await read('config/intent_contract.json');contract.as_of=now.slice(0,10);
await save('config/intent_contract.json',contract);
const accounts=JSON.parse(await shell("python3 -c 'import json; print(json.dumps([{\"company_name\":c[\"name\"],\"company_domain\":c[\"domain\"]} for c in json.load(open(\"config/accounts.json\"))]))'"));
if(accounts.length!==100)throw new Error('Expected exactly 100 canonical accounts.');
const cached=new Set(options.resume?JSON.parse(await shell("python3 -c 'import glob,json; print(json.dumps([json.load(open(p))[\"company_domain\"] for p in glob.glob(\"results/intent_v2/raw/research-*.json\") if json.load(open(p)).get(\"retrieved_at\")==json.load(open(\"config/intent_contract.json\"))[\"as_of\"]]))'")):[]);
const run={version:2,started_at:now,mode:options.resume?'resume':'refresh',fresh_accounts:0,cached_accounts:0,source_fetch_attempts:0,errors:[]};
for(let start=0;start<accounts.length;start+=4){
  const jobs=accounts.slice(start,start+4).map(async c=>{
    if(cached.has(c.company_domain)){run.cached_accounts++;return;}
    const queries=['"'+c.company_name+'" "'+c.company_domain+'" shipping software project','"'+c.company_name+'" shipping systems implementation hiring'];
    const result=await web({system2_search_query:queries.map(q=>({q})),response_length:'short'});
    await save(raw+'research-'+c.company_domain+'.json',{...c,routes:['project_announcement_search','implementation_hiring_search'],queries,retrieved_at:contract.as_of,result});run.fresh_accounts++;
  });
  const done=await Promise.allSettled(jobs);done.forEach((r,i)=>{if(r.status==='rejected')run.errors.push({stage:'search',domain:accounts[start+i].company_domain,error:String(r.reason)});});
  await save('results/intent_v2/live_run.json',run);
  if(options.onProgress)options.onProgress({researched:run.fresh_accounts,cached:run.cached_accounts});
}
const reviews=await read('config/intent_reviews.json');
const seen=new Set();
for(const entry of [...reviews.watchlist,...reviews.rejections,...reviews.qualified_claims]){
  if(!entry.source_url||!entry.source_fetch_receipt||seen.has(entry.source_url))continue;seen.add(entry.source_url);
  try{
    const result=await web({open:[{ref_id:entry.source_url}],response_length:'long'});
    await save(entry.source_fetch_receipt,{url:entry.source_url,retrieved_at:contract.as_of,result});run.source_fetch_attempts++;
  }catch(e){run.errors.push({stage:'fetch',url:entry.source_url,error:String(e)});}
}
await shell('python3 src/pipeline.py build');
run.summary=await read('results/intent_v2/summary.json');
// No people search is allowed until this account gate returns eligible rows.
const eligible=JSON.parse(await shell("python3 -c 'import csv,json; print(json.dumps([r[\"company_domain\"] for r in csv.DictReader(open(\"results/intent_v2/top_50_qualified.csv\"))]))'"));
run.eligible_contact_domains=eligible;
if(eligible.length){
  for(let start=0;start<eligible.length;start+=10){
    const r=await tools.mcp__codex_apps__clay_search_contacts({companyIdentifiers:eligible.slice(start,start+10),dslQuery:'select from people where experiences.any(is_current = true and seniority in ("C-suite", "VP", "Director", "Head") and job_title contains ("logistics", "supply", "ecommerce", "e-commerce", "operations", "COO", "CIO", "digital", "logistique", "logistica")) limit 2 by clay_company_id limit 20'});
    const payload=JSON.parse(r.content.find(c=>c.type==='text').text);
    const context=await tools.mcp__codex_apps__clay_get_task_context({taskId:payload.taskId});
    await save(raw+'people-'+start+'.json',JSON.parse(context.content.find(c=>c.type==='text').text));
  }
  await shell('python3 src/pipeline.py build');run.summary=await read('results/intent_v2/summary.json');
}
run.finished_at=(await tools.clock__curr_time({})).current_time;
run.billing='Tool credit cost not exposed; no Deepline Play executed.';
await save('results/intent_v2/live_run.json',run);await save('results/live_run.json',run);
return run;
