const $ = s => document.querySelector(s);
const fmt = n => new Intl.NumberFormat('fa-IR', {maximumFractionDigits: 0}).format(n || 0);
const statusNames = {resolved:'قطعی', pending_ai:'مأموریت باز', human_review:'بررسی انسانی', invalid:'نامعتبر'};
let activeTask = null;

function toast(message, error=false){const el=$('#toast');el.textContent=message;el.className='toast show'+(error?' error':'');setTimeout(()=>el.className='toast',3500)}
function loading(show,text='در حال خواندن ساختار فایل'){ $('#loader').classList.toggle('hidden',!show);$('#loaderText').textContent=text }
function escapeHtml(s){const d=document.createElement('div');d.textContent=s??'';return d.innerHTML}

function render(data){
  $('#documents').textContent=fmt(data.documents); $('#resolved').textContent=fmt(data.resolved);
  $('#pending').textContent=fmt(data.pending); $('#navPending').textContent=fmt(data.pending);
  $('#warningCount').textContent=fmt(data.warnings); $('#source').textContent=data.source;
  $('#debit').textContent=fmt(data.debit)+' ریال'; $('#credit').textContent=fmt(data.credit)+' ریال';
  $('#balance').textContent=fmt(Math.abs(data.balance));
  const balanced=Math.abs(data.balance)<1; $('#balanceStatus').textContent=balanced?'تراز و سالم':'نیازمند رسیدگی';
  $('#balanceStatus').style.color=balanced?'var(--green)':'var(--rose)';
  $('#missionCount').textContent=fmt(data.pending);
  $('#agentLog').innerHTML=[
    `<p><time>اکنون</time><span class="ok">✓</span>${fmt(data.lines)} ردیف از «${escapeHtml(data.source)}» خوانده شد.</p>`,
    `<p><time>مرحله ۲</time><span class="ok">✓</span>حروف، اعداد و تاریخ‌های شمسی نرمال شدند.</p>`,
    `<p><time>مرحله ۳</time><span class="${data.warnings?'wait':'ok'}">${data.warnings?'△':'✓'}</span>${fmt(data.documents)} سند کنترل شد؛ ${fmt(data.warnings)} هشدار ثبت شد.</p>`,
    `<p><time>مرحله ۴</time><span class="${data.pending?'wait':'ok'}">${data.pending?'✦':'✓'}</span>${data.pending?fmt(data.pending)+' ابهام به مأموریت آفلاین تبدیل شد.':'همه تصمیم‌ها قطعی هستند.'}</p>`,
    `<p><time>خروجی</time><span class="ok">✓</span>گزارش حرفه‌ای Excel آماده دانلود است.</p>`].join('');
  $('#taskList').innerHTML=data.tasks.length?data.tasks.map(t=>`<div class="task"><div class="task-icon">✦</div><div><h4>${escapeHtml(t.description)}</h4><p>سند ${escapeHtml(t.document)} · ${escapeHtml(t.date)} · ${t.debit?'بدهکار '+fmt(t.debit):'بستانکار '+fmt(t.credit)}</p></div><div class="task-actions"><a class="small-btn" href="/api/tasks/${t.task_id}/prompt">دریافت پرامپت</a><button class="small-btn accent" onclick="openAnswer('${t.task_id}')">ثبت پاسخ</button></div></div>`).join(''):'<div class="empty">همه‌چیز روشن است؛ مأموریت بازی وجود ندارد.</div>';
  $('#ledgerRows').innerHTML=data.recent_lines.map(l=>`<tr><td>${escapeHtml(l.document)}</td><td>${escapeHtml(l.date)}</td><td>${escapeHtml(l.description)}</td><td>${escapeHtml(l.account)}</td><td class="money">${fmt(l.debit)}</td><td class="money">${fmt(l.credit)}</td><td><span class="status ${l.status}">${statusNames[l.status]}</span></td></tr>`).join('');
  $('#warningList').innerHTML=data.warnings_list.length?data.warnings_list.map(w=>`<div class="warning-item"><i>△</i><b>${escapeHtml(w.message)}</b><span>${escapeHtml(w.code)}${w.document?' · سند '+escapeHtml(w.document):''}</span></div>`).join(''):'<div class="empty">هیچ هشدار کنترلی ثبت نشده است.</div>';
}
async function loadStatus(){try{const r=await fetch('/api/status');render(await r.json())}catch(e){toast('ارتباط با هسته آقا برقرار نشد.',true)}}
async function upload(file){if(!file)return;loading(true,'در حال کالبدشکافی دفتر و کنترل اسناد');const fd=new FormData();fd.append('file',file);try{const r=await fetch('/api/process',{method:'POST',body:fd});const data=await r.json();if(!r.ok)throw new Error(data.detail||'خطای پردازش');render(data);toast('عملیات تمام شد؛ گزارش تازه آماده است.')}catch(e){toast(e.message,true)}finally{loading(false)}}
function openAnswer(id){activeTask=id;$('#dialogTitle').textContent='پاسخ مأموریت '+id;$('#answerJson').value='';$('#answerDialog').showModal()}
window.openAnswer=openAnswer;
$('#submitAnswer').addEventListener('click',async()=>{let answer;try{answer=JSON.parse($('#answerJson').value)}catch{toast('JSON واردشده معتبر نیست.',true);return}loading(true,'در حال اعتبارسنجی پاسخ و ادامه عملیات');$('#answerDialog').close();try{const r=await fetch(`/api/tasks/${activeTask}/answer`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answer})});const data=await r.json();if(!r.ok)throw new Error(data.detail||'پاسخ رد شد');render(data);toast('پاسخ معتبر بود و در دفتر اعمال شد.')}catch(e){toast(e.message,true)}finally{loading(false)}});
const dz=$('#dropZone'),fi=$('#fileInput');fi.addEventListener('change',()=>upload(fi.files[0]));['dragenter','dragover'].forEach(e=>dz.addEventListener(e,x=>{x.preventDefault();dz.classList.add('drag')}));['dragleave','drop'].forEach(e=>dz.addEventListener(e,x=>{x.preventDefault();dz.classList.remove('drag')}));dz.addEventListener('drop',e=>upload(e.dataTransfer.files[0]));document.querySelectorAll('[data-scroll]').forEach(b=>b.onclick=()=>document.getElementById(b.dataset.scroll).scrollIntoView());loadStatus();
