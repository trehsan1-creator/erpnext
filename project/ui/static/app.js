const $ = s => document.querySelector(s);
const fmt = n => new Intl.NumberFormat('fa-IR', {maximumFractionDigits: 0}).format(n || 0);
const statusNames = {resolved:'قطعی', pending_ai:'مأموریت باز', human_review:'بررسی انسانی', invalid:'نامعتبر'};
let activeTask = null;
let activeParserTask = null;
let activeHumanTask = null;
let humanTaskMap = {};

function toast(message, error=false){const el=$('#toast');el.textContent=message;el.className='toast show'+(error?' error':'');setTimeout(()=>el.className='toast',3500)}
function loading(show,text='در حال خواندن ساختار فایل'){ $('#loader').classList.toggle('hidden',!show);$('#loaderText').textContent=text }
function escapeHtml(s){const d=document.createElement('div');d.textContent=s??'';return d.innerHTML}

function render(data){
  $('#parserLearning').classList.add('hidden');
  $('#profileCount').textContent=fmt((data.parser_profiles||[]).length);
  $('#activeProfile').textContent=data.active_profile||'Parser استاندارد آقا';
  $('#documents').textContent=fmt(data.documents); $('#resolved').textContent=fmt(data.resolved);
  $('#pending').textContent=fmt(data.pending); $('#navPending').textContent=fmt(data.pending);
  $('#warningCount').textContent=fmt(data.warnings); $('#source').textContent=data.source;
  $('#debit').textContent=fmt(data.debit)+' ریال'; $('#credit').textContent=fmt(data.credit)+' ریال';
  $('#balance').textContent=fmt(Math.abs(data.balance));
  const balanced=Math.abs(data.balance)<1; $('#balanceStatus').textContent=balanced?'تراز و سالم':'نیازمند رسیدگی';
  $('#balanceStatus').style.color=balanced?'var(--green)':'var(--rose)';
  $('#missionCount').textContent=fmt(data.pending);
  const humanItems=data.human_tasks||[];humanTaskMap=Object.fromEntries(humanItems.map(t=>[t.task_id,t]));
  $('#humanCount').textContent=fmt(humanItems.length);$('#navHuman').textContent=fmt(humanItems.length);
  $('#automationRate').textContent=fmt(data.automation_rate)+'٪';$('#automationFill').style.width=Math.min(100,data.automation_rate||0)+'%';
  $('#learnedRules').textContent=fmt((data.learning_stats||{}).promoted_rules||0);
  const priorityNames={critical:'فوری',high:'مهم',normal:'عادی',low:'کم'};
  $('#humanTaskList').innerHTML=humanItems.length?humanItems.map(t=>`<div class="human-card"><div class="human-icon">◎</div><div class="human-body"><h4>${escapeHtml(t.title)}</h4><p>${escapeHtml(t.reason)}</p><span class="context-line">${t.context.document_number?'سند '+escapeHtml(t.context.document_number):''} · ${fmt(t.fields.length)} ورودی لازم</span></div><div><span class="priority ${t.priority}">${priorityNames[t.priority]}</span><button class="small-btn accent" onclick="openHuman('${t.task_id}')">انجام کار</button></div></div>`).join(''):'<div class="empty">فعلاً کاری برای انسان وجود ندارد؛ آقا خودش جلو می‌رود.</div>';
  $('#agentLog').innerHTML=[
    `<p><time>اکنون</time><span class="ok">✓</span>${fmt(data.lines)} ردیف از «${escapeHtml(data.source)}» خوانده شد.</p>`,
    `<p><time>مرحله ۲</time><span class="ok">✓</span>حروف، اعداد و تاریخ‌های شمسی نرمال شدند.</p>`,
    `<p><time>مرحله ۳</time><span class="${data.warnings?'wait':'ok'}">${data.warnings?'△':'✓'}</span>${fmt(data.documents)} سند کنترل شد؛ ${fmt(data.warnings)} هشدار ثبت شد.</p>`,
    `<p><time>مرحله ۴</time><span class="${data.pending?'wait':'ok'}">${data.pending?'✦':'✓'}</span>${data.pending?fmt(data.pending)+' ابهام به مأموریت آفلاین تبدیل شد.':'همه تصمیم‌ها قطعی هستند.'}</p>`,
    `<p><time>خروجی</time><span class="ok">✓</span>گزارش حرفه‌ای Excel آماده دانلود است.</p>`].join('');
  $('#taskList').innerHTML=data.tasks.length?data.tasks.map(t=>`<div class="task"><div class="task-icon">✦</div><div><h4>${escapeHtml(t.description)}</h4><p>سند ${escapeHtml(t.document)} · ${escapeHtml(t.date)} · ${t.debit?'بدهکار '+fmt(t.debit):'بستانکار '+fmt(t.credit)}</p></div><div class="task-actions"><button class="small-btn" onclick="openPrompt('/api/tasks/${t.task_id}/prompt','پرامپت تحلیل تراکنش')">مشاهده پرامپت</button><button class="small-btn accent" onclick="openAnswer('${t.task_id}')">ثبت پاسخ</button></div></div>`).join(''):'<div class="empty">همه‌چیز روشن است؛ مأموریت بازی وجود ندارد.</div>';
  $('#ledgerRows').innerHTML=data.recent_lines.map(l=>`<tr><td>${escapeHtml(l.document)}</td><td>${escapeHtml(l.date)}</td><td>${escapeHtml(l.description)}</td><td>${escapeHtml(l.account)}</td><td class="money">${fmt(l.debit)}</td><td class="money">${fmt(l.credit)}</td><td><span class="status ${l.status}">${statusNames[l.status]}</span></td></tr>`).join('');
  $('#warningList').innerHTML=data.warnings_list.length?data.warnings_list.map(w=>`<div class="warning-item"><i>△</i><b>${escapeHtml(w.message)}</b><span>${escapeHtml(w.code)}${w.document?' · سند '+escapeHtml(w.document):''}</span></div>`).join(''):'<div class="empty">هیچ هشدار کنترلی ثبت نشده است.</div>';
}
async function loadStatus(){try{const r=await fetch('/api/status');render(await r.json())}catch(e){toast('ارتباط با هسته آقا برقرار نشد.',true)}}
function renderParserTask(data){
  activeParserTask=data.parser_task.task_id;
  $('#parserLearning').classList.remove('hidden');
  $('#parserReason').textContent=data.parser_task.reason+' — پرامپت آموزش آماده است؛ کانفیگ JSON را برگردان تا این قالب به حافظه آقا اضافه شود.';
  $('#parserPrompt').onclick=()=>openPrompt(`/api/parser-tasks/${activeParserTask}/prompt`,'پرامپت آموزش Parser');
  $('#profileCount').textContent=fmt((data.parser_profiles||[]).length);
  $('#parserLearning').scrollIntoView({behavior:'smooth',block:'center'});
}
async function upload(file){if(!file)return;loading(true,'در حال کالبدشکافی دفتر و کنترل اسناد');const fd=new FormData();fd.append('file',file);try{const r=await fetch('/api/process',{method:'POST',body:fd});const data=await r.json();if(!r.ok)throw new Error(data.detail||'خطای پردازش');if(data.needs_parser){renderParserTask(data);toast('قالب جدید است؛ مأموریت آموزش Parser ساخته شد.');return}render(data);toast('عملیات تمام شد؛ گزارش تازه آماده است.')}catch(e){toast(e.message,true)}finally{loading(false)}}
function openAnswer(id){activeTask=id;$('#dialogTitle').textContent='پاسخ مأموریت '+id;$('#answerJson').value='';$('#answerDialog').showModal()}
function fieldHtml(field){const required=field.required?'<em>*</em>':'';const help=field.help_text?`<small>${escapeHtml(field.help_text)}</small>`:'';const value=field.default??'';let control;if(field.field_type==='select'){control=`<select data-key="${field.key}"><option value="">انتخاب کن…</option>${field.options.map(o=>`<option value="${escapeHtml(o.value)}" ${String(value)===String(o.value)?'selected':''}>${escapeHtml(o.label)}</option>`).join('')}</select>`}else if(field.field_type==='textarea'){control=`<textarea data-key="${field.key}" placeholder="${escapeHtml(field.placeholder||'')}">${escapeHtml(value)}</textarea>`}else if(field.field_type==='boolean'){return `<div class="field-group boolean-field"><input data-key="${field.key}" type="checkbox" ${value?'checked':''}><label>${escapeHtml(field.label)} ${required}</label>${help}</div>`}else{const type=field.field_type==='number'?'number':field.field_type==='date'?'date':'text';control=`<input data-key="${field.key}" type="${type}" value="${escapeHtml(value)}" placeholder="${escapeHtml(field.placeholder||'')}">`}return `<div class="field-group"><label>${escapeHtml(field.label)} ${required}</label>${control}${help}</div>`}
function openHuman(id){const task=humanTaskMap[id];if(!task)return;activeHumanTask=id;$('#humanDialogTitle').textContent=task.title;$('#humanInstructions').textContent=task.instructions;const c=task.context||{};$('#humanContext').innerHTML=[c.document_number&&`<b>سند:</b> ${escapeHtml(c.document_number)}`,c.jalali_date&&`<b>تاریخ:</b> ${escapeHtml(c.jalali_date)}`,c.description&&`<b>شرح:</b> ${escapeHtml(c.description)}`,c.debit&&`<b>بدهکار:</b> ${fmt(c.debit)}`,c.credit&&`<b>بستانکار:</b> ${fmt(c.credit)}`].filter(Boolean).join(' · ');$('#humanForm').innerHTML=task.fields.map(fieldHtml).join('');$('#humanDialog').classList.remove('hidden');document.body.classList.add('modal-open')}
function closeHuman(){activeHumanTask=null;$('#humanDialog').classList.add('hidden');document.body.classList.remove('modal-open')}
async function openPrompt(url,title){loading(true,'در حال آماده‌سازی پرامپت');try{const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw new Error('پرامپت پیدا نشد');const text=await r.text();$('#promptTitle').textContent=title;$('#promptText').value=text;$('#promptChars').textContent=fmt(text.length)+' کاراکتر';$('#copyPrompt').innerHTML='<span>□</span> کپی کامل پرامپت';$('#promptDialog').classList.remove('hidden');document.body.classList.add('modal-open')}catch(e){toast(e.message,true)}finally{loading(false)}}
function closePrompt(){const modal=$('#promptDialog');modal.classList.add('hidden');document.body.classList.remove('modal-open')}
async function copyPrompt(){const text=$('#promptText').value;if(!text)return;try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(text)}else{$('#promptText').focus();$('#promptText').select();document.execCommand('copy');window.getSelection()?.removeAllRanges()}$('#copyPrompt').innerHTML='<span>✓</span> پرامپت کپی شد';toast('پرامپت کامل در کلیپ‌بورد کپی شد.')}catch{toast('کپی خودکار ممکن نشد؛ متن را دستی انتخاب کن.',true)}}
window.openAnswer=openAnswer;window.openPrompt=openPrompt;window.openHuman=openHuman;
$('#copyPrompt').addEventListener('click',copyPrompt);
$('#closePrompt').addEventListener('click',closePrompt);$('#cancelPrompt').addEventListener('click',closePrompt);
$('#promptDialog').addEventListener('click',event=>{if(event.target===$('#promptDialog'))closePrompt()});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!$('#promptDialog').classList.contains('hidden'))closePrompt();if(event.key==='Escape'&&!$('#humanDialog').classList.contains('hidden'))closeHuman()});
$('#closeHuman').addEventListener('click',closeHuman);$('#cancelHuman').addEventListener('click',closeHuman);$('#humanDialog').addEventListener('click',event=>{if(event.target===$('#humanDialog'))closeHuman()});
$('#submitHuman').addEventListener('click',async()=>{if(!activeHumanTask)return;const answers={};$('#humanForm').querySelectorAll('[data-key]').forEach(el=>{answers[el.dataset.key]=el.type==='checkbox'?el.checked:el.value});loading(true,'در حال اعمال پاسخ و به‌روزرسانی حافظه تصمیم');const taskId=activeHumanTask;closeHuman();try{const r=await fetch(`/api/human-tasks/${taskId}/resolve`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answer:answers})});const data=await r.json();if(!r.ok)throw new Error(data.detail||'ثبت پاسخ ممکن نشد');render(data);toast('پاسخ ثبت شد؛ آقا عملیات را ادامه داد و حافظه‌اش به‌روز شد.')}catch(e){toast(e.message,true)}finally{loading(false)}});
$('#submitAnswer').addEventListener('click',async()=>{let answer;try{answer=JSON.parse($('#answerJson').value)}catch{toast('JSON واردشده معتبر نیست.',true);return}loading(true,'در حال اعتبارسنجی پاسخ و ادامه عملیات');$('#answerDialog').close();try{const r=await fetch(`/api/tasks/${activeTask}/answer`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answer})});const data=await r.json();if(!r.ok)throw new Error(data.detail||'پاسخ رد شد');render(data);toast('پاسخ معتبر بود و در دفتر اعمال شد.')}catch(e){toast(e.message,true)}finally{loading(false)}});
$('#parserConfigInput').addEventListener('change',async event=>{const file=event.target.files[0];if(!file||!activeParserTask)return;let answer;try{answer=JSON.parse(await file.text())}catch{toast('فایل کانفیگ JSON معتبر نیست.',true);return}loading(true,'در حال اعتبارسنجی، آزمایش و یادگیری قالب جدید');try{const r=await fetch(`/api/parser-tasks/${activeParserTask}/config`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answer})});const data=await r.json();if(!r.ok)throw new Error(data.detail||'کانفیگ رد شد');render(data);toast('قالب جدید با موفقیت یاد گرفته شد و فایل پردازش شد.')}catch(e){toast(e.message,true)}finally{loading(false);event.target.value=''}});
const dz=$('#dropZone'),fi=$('#fileInput');fi.addEventListener('change',()=>upload(fi.files[0]));['dragenter','dragover'].forEach(e=>dz.addEventListener(e,x=>{x.preventDefault();dz.classList.add('drag')}));['dragleave','drop'].forEach(e=>dz.addEventListener(e,x=>{x.preventDefault();dz.classList.remove('drag')}));dz.addEventListener('drop',e=>upload(e.dataTransfer.files[0]));document.querySelectorAll('[data-scroll]').forEach(b=>b.onclick=()=>document.getElementById(b.dataset.scroll).scrollIntoView());loadStatus();
