// Exercise the actual page script's state transitions in a minimal DOM harness.
// This checks browser storage/reload/export logic, not rendered visual layout.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const html=fs.readFileSync('results/outbound_v1/campaign.html','utf8');
const initial=html.match(/<script id="initial" type="application\/json">([\s\S]*?)<\/script>/)[1];
const code=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const saved=new Map();let downloaded;
class Element{constructor(){this.children=[];this.textContent='';this.value=''}append(...x){this.children.push(...x)}replaceChildren(...x){this.children=x}setAttribute(){}click(){}select(){}}
function start(){const ids=new Map();for(const id of ['initial','connection','metrics','search','filter','list','detail','save_status','backup','current_csv'])ids.set(id,new Element());ids.get('initial').textContent=initial;ids.get('filter').value='all';
 class LocalURL extends URL{static createObjectURL(blob){downloaded=blob;return 'blob:test'}static revokeObjectURL(){}}
 const context=vm.createContext({console,URL:LocalURL,Blob,crypto:crypto.webcrypto,location:{protocol:'file:'},localStorage:{getItem:k=>saved.get(k)||null,setItem:(k,v)=>saved.set(k,v)},document:{getElementById:id=>ids.get(id),createElement:()=>new Element()},navigator:{clipboard:{writeText:async()=>{}}},setTimeout:f=>{f()},alert:msg=>{throw Error(msg)}});vm.runInContext(code,context);return {context,ids};}
(async()=>{let a=start();assert.equal(a.ids.get('list').children.length,50);const cid=vm.runInContext('data.contacts[0].id',a.context);
 await vm.runInContext(`send({action:'note',contact_id:${JSON.stringify(cid)},note:'Keep the real owner visible'})`,a.context);
 await vm.runInContext(`send({action:'review',contact_id:${JSON.stringify(cid)},status:'reviewed'})`,a.context);
 a=start();assert.equal(vm.runInContext('data.contacts[0].note',a.context),'Keep the real owner visible');assert.equal(vm.runInContext('data.contacts[0].review_status',a.context),'reviewed');assert.equal(vm.runInContext('data.contacts[0].messages[0].review_status',a.context),'reviewed');
 await vm.runInContext(`send({action:'edit_message',contact_id:${JSON.stringify(cid)},message_id:data.contacts[0].messages[0].id,subject:'Edited subject',body:data.contacts[0].messages[0].body,revision:data.contacts[0].messages[0].revision})`,a.context);
 a=start();assert.equal(vm.runInContext('data.contacts[0].messages[0].subject',a.context),'Edited subject');assert.equal(vm.runInContext('data.contacts[0].review_status',a.context),'unreviewed');assert.equal(vm.runInContext('data.summary.sent',a.context),0);
 a.ids.get('current_csv').onclick();assert.ok((await downloaded.text()).includes('Edited subject'));a.ids.get('backup').onclick();assert.ok((await downloaded.text()).includes('Keep the real owner visible'));
 a.ids.get('search').value='Quince';a.ids.get('search').oninput();assert.equal(a.ids.get('list').children.length,1);
 console.log('Dashboard storage, review, edit, reload, search and export checks passed.');})().catch(e=>{console.error(e);process.exitCode=1});
