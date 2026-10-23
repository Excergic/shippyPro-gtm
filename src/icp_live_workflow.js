/* Run in a connected Codex functions.exec tool context; see RUNBOOK.md.
 * This file is an AsyncFunction body receiving (tools, options).
 * No mocked providers, invented records, or outreach actions.
 */
const root = options.root || '/Volumes/SeagateSSD/Projects/gtm-engineering/signoz';
const raw = 'deepline/data/shippypro-live/raw/';
const decode = r => {
  if(r.isError) throw new Error(JSON.stringify(r.content));
  return JSON.parse(r.content.find(c => c.type === 'text').text);
};
async function shell(cmd) {
  const r = await tools.exec_command({cmd, workdir:root, max_output_tokens:18000});
  if(r.exit_code !== 0) throw new Error(r.output);
  return r.output;
}
async function save(path, data) {
  const value = typeof data === 'string' ? data : JSON.stringify(data,null,2);
  return tools.apply_patch('*** Begin Patch\n*** Add File: '+root+'/'+path+'\n+'+value.split('\n').join('\n+')+'\n*** End Patch');
}
async function read(path) { return JSON.parse(await shell('cat '+path)); }
const settings = await read('config/settings.json');
const timestamp = (await tools.clock__curr_time({})).current_time;
settings.as_of=timestamp.slice(0,10);
await save('config/settings.json',settings);
const runId='live-'+timestamp.replace(/[^0-9]/g,'');
const manifest={run_id:runId,started_at:timestamp,mode:options.discover?'discover':'refresh',stages:[],errors:[]};
await save('results/live_run.json',manifest);
let accounts=JSON.parse(await shell("python3 -c 'import json; print(json.dumps([{\"name\":c[\"name\"],\"domain\":c[\"domain\"]} for c in json.load(open(\"config/accounts.json\"))]))'"));
if(options.discover) {
  const excluded=new Set(settings.suppressed_domains);
  const oldExclusions=await read('results/excluded.json');
  oldExclusions.filter(c=>c.domain).forEach(c=>excluded.add(c.domain));
  const dsl='select from companies where industry in ("Retail Apparel and Fashion", "Apparel and Fashion", "Cosmetics", "Sporting Goods", "Luxury Goods and Jewelry", "Online and Mail Order Retail") and locations.any(is_headquarters = true and country_name in ("Italy", "France", "United Kingdom", "Spain", "Germany")) limit 140';
  let page=decode(await tools.mcp__codex_apps__clay_search_companies({dslQuery:dsl}));
  const seen=new Set();const candidates=[];
  for(let n=0;n<7;n++) {
    await save(raw+runId+'-discovery-'+n+'.json',page);
    for(const c of Object.values(page.companies||{})) {
      if(!c.domain||!/^[a-z0-9.-]+\.[a-z]{2,}$/.test(c.domain)||seen.has(c.domain)||excluded.has(c.domain))continue;
      if(!settings.geographies.includes(c.country))continue;
      seen.add(c.domain);candidates.push({...c,discovery_task_id:page.taskId});
    }
    if(!page.hasMore||candidates.length>=100)break;
    page=decode(await tools.mcp__codex_apps__clay_load_more_search_results({taskId:page.taskId}));
  }
  if(candidates.length<100)throw new Error('Discovery returned '+candidates.length+' acceptable candidates. Inspect exclusions and supplement the source population; no fabricated padding.');
  accounts=candidates.slice(0,100);await save('config/accounts.json',accounts);
  manifest.stages.push({stage:'discovery',accepted:accounts.length});
}
// Modest bounded concurrency; errors are receipts, never empty successful results.
for(let start=0;start<accounts.length;start+=4) {
  const outcomes=await Promise.allSettled(accounts.slice(start,start+4).map(async c=>{
    const q='"'+c.name+'" "'+c.domain+'" shipping delivery logistics ecommerce expansion '+(Number(settings.as_of.slice(0,4))-1)+' '+settings.as_of.slice(0,4);
    const response=await tools.web__run({search_query:[{q}],response_length:'short'});
    await save(raw+'web-'+c.domain+'.json',{domain:c.domain,company_name:c.name,query:q,retrieved_at:settings.as_of,response,run_id:runId});
    return c.domain;
  }));
  outcomes.forEach((r,i)=>{if(r.status==='rejected')manifest.errors.push({stage:'research',domain:accounts[start+i].domain,error:String(r.reason)});});
  manifest.researched=Math.min(start+4,accounts.length);await save('results/live_run.json',manifest);
}
await shell('python3 src/pipeline.py build');
const top=JSON.parse(await shell("python3 -c 'import csv,json; print(json.dumps([{\"company_domain\":r[\"company_domain\"]} for r in csv.DictReader(open(\"results/top_50_qualified.csv\"))]))'"));
const queries=[
 'select from people where experiences.any(is_current = true and seniority in ("C-suite", "VP", "Director", "Head") and job_title is_similar_to ("Chief Operating Officer", "Chief Supply Chain Officer", "Head of Logistics", "Supply Chain Director", "Ecommerce Director", "Head of Fulfilment", "Chief Information Officer")) limit 2 by clay_company_id limit 20',
 'select from people where experiences.any(is_current = true and seniority in ("C-suite", "VP", "Director", "Head") and job_title contains ("logistics", "supply", "ecommerce", "e-commerce", "operations", "COO", "CIO", "digital", "logistique", "logistica")) limit 2 by clay_company_id limit 20'
];
let pending=top.map(c=>c.company_domain);
for(let route=0;route<queries.length;route++) {
  for(let start=0;start<pending.length;start+=10) {
    const domains=pending.slice(start,start+10);
    try {
      const search=decode(await tools.mcp__codex_apps__clay_search_contacts({companyIdentifiers:domains,dslQuery:queries[route]}));
      const context=decode(await tools.mcp__codex_apps__clay_get_task_context({taskId:search.taskId}));
      await save(raw+'contacts-'+runId+'-'+route+'-'+start+'.json',context);
      manifest.stages.push({stage:'contacts',route,task_id:context.taskId,input_domains:domains,returned:context.contacts.length});
    }catch(e){manifest.errors.push({stage:'contacts',route,domains,error:String(e)});}
    await save('results/live_run.json',manifest);
  }
  await shell('python3 src/pipeline.py build');
  pending=JSON.parse(await shell("python3 -c 'import csv,json; print(json.dumps([r[\"company_domain\"] for r in csv.DictReader(open(\"results/top_50_qualified.csv\")) if r[\"decision_makers_found\"]==\"0\"]))'"));
}
manifest.finished_at=(await tools.clock__curr_time({})).current_time;
manifest.summary=await read('results/summary.json');
manifest.unresolved_domains=pending;manifest.credit_cost='unavailable from connected provider';
await save('results/live_run.json',manifest);
return manifest;
