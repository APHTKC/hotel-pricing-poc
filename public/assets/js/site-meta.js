const LABELS={zh:{version:'版本',build:'Build',data:'資料更新',views:'瀏覽次數'},en:{version:'Version',build:'Build',data:'Data updated',views:'Views'},ja:{version:'バージョン',build:'Build',data:'データ更新',views:'閲覧数'}};
const lang=()=>{const value=document.documentElement.lang||'zh';return value.toLowerCase().startsWith('en')?'en':value.toLowerCase().startsWith('ja')?'ja':'zh'};
const load=path=>fetch(`${path}?v=${Date.now()}`,{cache:'no-store'}).then(response=>{if(!response.ok)throw Error(`HTTP ${response.status}`);return response.json()});

function renderMeta(meta,count=null){
  const footer=document.querySelector('footer.source-note,.source-note');
  if(!footer)return;
  let node=document.querySelector('#siteMeta');
  if(!node){node=document.createElement('span');node.id='siteMeta';node.className='site-meta';footer.appendChild(node)}
  const labels=LABELS[lang()];
  const items=[`${labels.version} ${meta.version||'—'}`,`${labels.build} ${meta.build||'—'}`];
  if(meta.data_updated_at){const date=new Date(meta.data_updated_at);items.push(`${labels.data} ${Number.isNaN(date.valueOf())?meta.data_updated_at:new Intl.DateTimeFormat(document.documentElement.lang||'zh-TW',{dateStyle:'medium',timeZone:'Asia/Taipei'}).format(date)}`)}
  if(count!=null&&count!=='')items.push(`${labels.views} ${count}`);
  node.textContent=items.join(' · ');
}

async function enableCounter(config,meta){
  const code=String(config.site_code||'').trim().toLowerCase();
  if(!config.enabled||!code||!/^[a-z0-9-]+$/.test(code))return;
  const endpoint=`https://${code}.goatcounter.com/count`;
  const script=document.createElement('script');
  script.async=true;script.src='https://gc.zgo.at/count.js';script.dataset.goatcounter=endpoint;
  document.head.appendChild(script);
  try{const result=await load(`https://${code}.goatcounter.com/counter/${encodeURIComponent(config.count_scope||'TOTAL')}.json`);renderMeta(meta,result.count)}catch(_error){/* The page remains usable and simply omits the counter. */}
}

Promise.all([load('./data/site_meta.json'),load('./data/analytics.json').catch(()=>({enabled:false}))]).then(([meta,analytics])=>{renderMeta(meta);enableCounter(analytics,meta)}).catch(()=>{});
document.addEventListener('change',()=>setTimeout(()=>load('./data/site_meta.json').then(renderMeta).catch(()=>{}),0));
