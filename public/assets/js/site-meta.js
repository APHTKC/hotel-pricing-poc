const LABELS={zh:{version:'版本',build:'Build',data:'資料更新',views:'瀏覽次數'},en:{version:'Version',build:'Build',data:'Data updated',views:'Views'},ja:{version:'バージョン',build:'Build',data:'データ更新',views:'閲覧数'}};
const lang=()=>{const value=document.documentElement.lang||'zh';return value.toLowerCase().startsWith('en')?'en':value.toLowerCase().startsWith('ja')?'ja':'zh'};
const load=path=>fetch(`${path}?v=${Date.now()}`,{cache:'no-store'}).then(response=>{if(!response.ok)throw Error(`HTTP ${response.status}`);return response.json()});
let metaNode=null,cachedMeta=null,cachedAnalytics=null;

function renderMeta(meta){
  const footer=document.querySelector('footer.source-note,.source-note');
  if(!footer)return;
  let node=metaNode||document.querySelector('#siteMeta');
  if(!node){node=document.createElement('span');node.id='siteMeta';node.className='site-meta';metaNode=node}
  if(!node.isConnected)footer.appendChild(node);
  let copy=node.querySelector('.site-meta-copy');
  if(!copy){copy=document.createElement('span');copy.className='site-meta-copy';node.prepend(copy)}
  const labels=LABELS[lang()];
  const items=[`${labels.version} ${meta.version||'—'}`,`${labels.build} ${meta.build||'—'}`];
  if(meta.data_updated_at){const date=new Date(meta.data_updated_at);items.push(`${labels.data} ${Number.isNaN(date.valueOf())?meta.data_updated_at:new Intl.DateTimeFormat(document.documentElement.lang||'zh-TW',{dateStyle:'medium',timeZone:'Asia/Taipei'}).format(date)}`)}
  copy.textContent=items.join(' · ');
  const counter=node.querySelector('.site-counter');
  if(counter){counter.querySelector('.site-counter-label').textContent=labels.views;counter.querySelector('img').alt=labels.views}
}

function enableCounter(config){
  const site=String(config.site||'').trim().toLowerCase();
  if(!config.enabled||config.provider!=='librecounter'||!site||!/^[a-z0-9.-]+$/.test(site))return;
  const node=document.querySelector('#siteMeta');
  if(!node||node.querySelector('.site-counter'))return;
  const labels=LABELS[lang()];
  const separator=document.createElement('span');separator.className='site-meta-separator';separator.textContent='·';
  const link=document.createElement('a');link.className='site-counter';link.href=`https://librecounter.org/${encodeURIComponent(site)}/show`;link.target='_blank';link.rel='noopener noreferrer';link.title=labels.views;
  const label=document.createElement('span');label.className='site-counter-label';label.textContent=labels.views;
  const image=document.createElement('img');image.src='https://librecounter.org/counter.svg';image.referrerPolicy='unsafe-url';image.alt=labels.views;image.width=44;image.height=12;
  image.addEventListener('error',()=>{separator.remove();link.remove()},{once:true});
  link.append(label,image);node.append(separator,link);
}

function mount(){if(!cachedMeta)return;renderMeta(cachedMeta);enableCounter(cachedAnalytics||{enabled:false})}
Promise.all([load('./data/site_meta.json'),load('./data/analytics.json').catch(()=>({enabled:false}))]).then(([meta,analytics])=>{cachedMeta=meta;cachedAnalytics=analytics;mount();const footer=document.querySelector('footer.source-note,.source-note');if(footer)new MutationObserver(()=>{if(metaNode&&!metaNode.isConnected)mount()}).observe(footer,{childList:true})}).catch(()=>{});
document.addEventListener('change',()=>setTimeout(mount,0));
