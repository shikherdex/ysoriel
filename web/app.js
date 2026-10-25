const starCanvas = document.querySelector('#stars');
const starCtx = starCanvas.getContext('2d');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let stars = [];
let starWidth = 0;
let starHeight = 0;

function resizeStars() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  starWidth = window.innerWidth;
  starHeight = window.innerHeight;
  starCanvas.width = starWidth * dpr;
  starCanvas.height = starHeight * dpr;
  starCanvas.style.width = `${starWidth}px`;
  starCanvas.style.height = `${starHeight}px`;
  starCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const count = Math.min(250, Math.floor(starWidth * starHeight / 5200));
  stars = Array.from({ length: count }, () => ({
    x: Math.random() * starWidth,
    y: Math.random() * starHeight,
    r: Math.random() * 1.35 + .2,
    phase: Math.random() * Math.PI * 2,
    speed: .35 + Math.random() * .75,
    tint: Math.random() > .86 ? '190,177,255' : '219,226,255'
  }));
  drawStars(0);
}

function drawStars(time) {
  starCtx.clearRect(0, 0, starWidth, starHeight);
  for (const star of stars) {
    const shimmer = reducedMotion ? .78 : .55 + .45 * Math.sin(time * .001 * star.speed + star.phase);
    starCtx.beginPath();
    starCtx.arc(star.x, star.y, star.r, 0, Math.PI * 2);
    starCtx.fillStyle = `rgba(${star.tint},${.2 + shimmer * .68})`;
    starCtx.shadowBlur = star.r > 1 ? 5 : 0;
    starCtx.shadowColor = `rgba(${star.tint},.65)`;
    starCtx.fill();
  }
  starCtx.shadowBlur = 0;
  if (!reducedMotion) requestAnimationFrame(drawStars);
}
window.addEventListener('resize', resizeStars, { passive: true });
resizeStars();

const toast = document.querySelector('#toast');
let toastTimer;
function showToast(message) {
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 2600);
}


/* ---------- helpers ---------- */
const $ = s => document.querySelector(s);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const inr = n => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });
const dayStart = d => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const smooth = reducedMotion ? 'auto' : 'smooth';

async function api(path, payload) {
  const res = await fetch('/api' + path, payload === undefined ? undefined : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  });
  let data = {};
  try { data = await res.json(); } catch { /* non-JSON error page */ }
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

/* Minimal, safe markdown for agent answers: escape first, then add structure. */
function md(text) {
  const inline = s => s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[\s(])\*(?!\s)(.+?)\*(?=[\s).,!?:;]|$)/g, '$1<em>$2</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>');
  let out = '', list = false;
  for (const raw of esc(text).split('\n')) {
    const line = raw.trimEnd();
    const li = line.match(/^\s*(?:[-*•]|\d+\.)\s+(.*)/);
    if (li) { if (!list) { out += '<ul>'; list = true; } out += `<li>${inline(li[1])}</li>`; continue; }
    if (list) { out += '</ul>'; list = false; }
    const h = line.match(/^#{1,4}\s+(.*)/);
    if (h) out += `<h4>${inline(h[1])}</h4>`;
    else if (line.trim()) out += `<p>${inline(line)}</p>`;
  }
  return out + (list ? '</ul>' : '');
}

function when(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return '';
  const t = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  const diff = Math.round((dayStart(new Date()) - dayStart(d)) / 864e5);
  if (diff === 0) return `Today at ${t}`;
  if (diff === 1) return `Yesterday at ${t}`;
  return `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} at ${t}`;
}
function ago(iso) {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  if (m < 1) return 'just now';
  if (m < 60) return `${m} min ago`;
  if (m < 1440) return `${Math.round(m / 60)} h ago`;
  return `${Math.round(m / 1440)} d ago`;
}
function clock(hhmm) {
  const [h, m] = String(hhmm).split(':').map(Number);
  return [`${((h + 11) % 12) + 1}:${String(m).padStart(2, '0')}`, h >= 12 ? 'PM' : 'AM'];
}
const dayLabel = iso => new Date(iso + 'T00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });

/* ---------- state + rendering ---------- */
let S = null;
let busy = false;
const AVATARS = ['violet', 'blue', 'teal', 'amber', 'pink'];
const agentOf = key => S?.agents.find(a => a.key === key);
const glyph = key => agentOf(key)?.glyph || '✧';
const agentName = key => agentOf(key)?.name || key;
let crewOpen = false;

async function refresh() {
  try { S = await api('/state'); render(); }
  catch (e) { showToast('Can’t reach the Ysoriel server. Is app.py running?'); }
}

function render() {
  const today = new Date();
  const first = (S.name || '').split(' ')[0];
  const hour = today.getHours();
  const part = hour < 12 ? 'morning' : hour < 17 ? 'afternoon' : 'evening';
  $('#greeting').textContent = `Good ${part}${first ? ', ' + first : ''}`;
  $('#eyebrowDate').textContent = today.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }).toUpperCase();
  $('#datePill').textContent = today.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
  const initial = (S.name || 'Y').trim()[0].toUpperCase();
  $('#profileAvatar').textContent = initial;
  $('#topAvatar').textContent = initial;
  $('#profileName').textContent = S.name || 'You';

  renderMetrics(); renderCrew(); renderMissions(); renderAgenda();
  renderApprovals(); renderActivity(); renderMoney(); renderReminders();
}

function renderMetrics() {
  const todays = S.events.filter(e => e.date === S.today);
  $('#mEvents').innerHTML = `${todays.length} <small>${todays.length === 1 ? 'event' : 'events'} today</small>`;
  $('#mEventsFoot').innerHTML = todays.length ? `First up at <strong>${clock(todays[0].start).join(' ')}</strong>` : 'Nothing scheduled today';

  const open = S.reminders.filter(r => !r.done);
  const overdue = open.filter(r => r.due < S.today).length;
  $('#mRem').innerHTML = `${open.length} <small>open</small>`;
  $('#mRemFoot').textContent = overdue ? `${overdue} overdue` : open.length ? `Next due ${dayLabel(open[0].due)}` : 'All clear';
  $('#mRemBar').style.width = open.length ? `${Math.round((open.length - overdue) / open.length * 100)}%` : '0%';

  const p = S.pending.length;
  $('#mAppr').innerHTML = `${p} <small>${p === 1 ? 'approval' : 'approvals'}</small>`;
  $('#mApprFoot').textContent = p ? 'Waiting for your decision' : 'Nothing waiting';

  const ready = S.agents.length - S.paused;
  const used = S.agents.filter(a => a.key !== 'chief' && a.last).length;
  $('#mCrew').innerHTML = `${ready} <small>of ${S.agents.length} ready</small>`;
  $('#mCrewFoot').textContent = S.running ? 'Working on a request now' : used ? `${used} used in the last request` : S.paused ? `${S.paused} paused` : 'Standing by';
  $('#notifDot').hidden = !p;
}

function renderCrew() {
  const list = $('#agentList');
  list.classList.toggle('expanded', crewOpen);
  list.innerHTML = S.agents.map((a, i) => `
    <button class="agent-row${i >= 5 ? ' extra' : ''}" data-agent="${esc(a.key)}">
      <span class="agent-avatar avatar-${AVATARS[i % 5]}">${esc(a.glyph)}</span><span class="agent-name">${esc(a.name)}</span>
      <i class="status-dot ${a.status === 'active' ? 'online' : a.status === 'paused' ? 'paused' : 'idle'}"></i></button>`).join('');
  $('#crewButton').innerHTML = crewOpen ? 'Show fewer <span>↑</span>' : `View all ${S.agents.length} agents <span>→</span>`;
}

function missionHTML(j) {
  const key = j.agents[0] || 'chief';
  const state = j.status === 'running' ? ['state-research', 'WORKING'] : j.status === 'done' ? ['state-preparing', 'DONE'] : ['state-failed', 'NEEDS ATTENTION'];
  const names = j.agents.slice(0, 2).map(agentName).join(' + ') + (j.agents.length > 2 ? ` +${j.agents.length - 2}` : '');
  const blurb = j.status === 'running' ? (j.log[j.log.length - 1] || 'Planning…') : (j.answer || '').replace(/^\s*[-*•]\s+/gm, '').replace(/[#*`]/g, '').replace(/\s*\n+\s*/g, ' · ').slice(0, 110) + ((j.answer || '').length > 110 ? '…' : '');
  const dot = j.status === 'done' ? 'teal' : 'violet';
  return `<article class="mission-item"><div class="mission-symbol sym-${dot}">${esc(glyph(key))}</div><div class="mission-body">
    <div class="mission-title-line"><h3>${esc(j.q.length > 60 ? j.q.slice(0, 60) + '…' : j.q)}</h3><span class="mission-state ${state[0]}">${state[1]}</span></div>
    <p>${esc(blurb)}</p>
    <div class="mission-meta"><span><i class="micro-dot ${dot}-dot"></i>${esc(names || 'Chief of Staff')}</span><span>Updated ${ago(j.updated)}</span></div>
    <div class="mission-progress"><span class="${dot}-progress" style="width:${j.pct}%"></span></div></div>
    <button class="row-arrow" data-job="${esc(j.id)}" aria-label="Open mission">↗</button></article>`;
}
function renderMissions() {
  const n = S.jobs.length;
  $('#navMissions').hidden = !n; $('#navMissions').textContent = n;
  $('#missionList').innerHTML = n ? S.jobs.slice(0, 3).map(missionHTML).join('')
    : '<div class="empty-note">No missions yet. Ask Ysoriel something above and it will show up here.</div>';
  $('#allMissions').hidden = n <= 3;
}

let showPast = false;
const isoPlus = n => { const d = new Date(S.today + 'T00:00'); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
function renderAgenda() {
  $('#togglePast').textContent = showPast ? 'Hide past days' : 'Show past days';
  const evs = S.events.map((e, i) => ({ ...e, i })).filter(e => showPast || e.date >= S.today);
  const byDay = {};
  evs.forEach(e => (byDay[e.date] ||= []).push(e));
  const days = Object.keys(byDay).sort();
  $('#agendaList').innerHTML = days.length ? days.map(date => {
    const name = date === S.today ? 'Today' : date === isoPlus(1) ? 'Tomorrow' : date < S.today ? 'Earlier' : '';
    const items = byDay[date].map(e => {
      const [t, ap] = clock(e.start);
      return `<article class="agenda-item"><div class="agenda-time">${t}<small>${ap}</small></div><div class="agenda-marker"><i></i></div>
        <div class="agenda-info"><h3>${esc(e.title)}</h3><p>${e.duration} min</p></div>
        <span class="agenda-end"><span class="event-tag ${date === S.today ? 'tag-focus' : 'tag-work'}">${e.duration} MIN</span><button class="del-btn" data-del-event="${e.i}" aria-label="Delete ${esc(e.title)}" title="Delete">×</button></span></article>`;
    }).join('');
    return `<div class="day-group"><div class="day-head"><span><strong>${name || esc(dayLabel(date))}</strong>${name ? ' · ' + esc(dayLabel(date)) : ''}</span><button class="mini-link" data-clear-day="${esc(date)}">Clear day</button></div>${items}</div>`;
  }).join('') : '<div class="empty-note">Nothing scheduled. Try “Add dentist tomorrow at 5 pm”.</div>';
}

const KIND = { booking: ['⌂', ''], purchase: ['◇', ''], send_message: ['✉', 'mail-icon'], delete_memory: ['◉', 'mail-icon'] };
function renderApprovals() {
  $('#approvalCount').textContent = S.pending.length;
  $('#approvalList').innerHTML = S.pending.length ? S.pending.map(a => {
    const [icon, cls] = KIND[a.kind] || ['◈', ''];
    return `<article class="approval-item"><span class="approval-icon ${cls}">${icon}</span><div class="approval-copy">
      <h3>${esc(a.summary)}</h3><p>Request #${a.id}</p><span class="approval-context">Requested by ${esc(agentLabel(a.agent))} · ${esc(when(a.created))}</span></div>
      <button class="review-button" data-review="${a.id}">Review</button></article>`;
  }).join('') : '<div class="approval-empty">You’re all clear. No approvals waiting.</div>';
}
const agentLabel = k => (S.agents.find(a => a.key === k || (k === 'communication' && a.key === 'comms')) || { name: k }).name;

function renderActivity() {
  const icon = { mint: '✓', violet: '✧', blue: '◈' };
  $('#activityList').innerHTML = S.activity.length ? S.activity.map(a => `
    <article class="activity-item"><span class="activity-icon act-${a.tone}">${icon[a.tone] || '✧'}</span>
    <div><p><strong>${esc(a.who)}</strong> ${esc(a.text)}</p><time>${esc(when(a.t))}</time></div></article>`).join('')
    : '<div class="empty-note">Nothing yet. Activity shows up as agents work for you.</div>';
}

function renderMoney() {
  const m = S.money;
  if (!m.budget && !m.spent && !Object.keys(m.by_category).length) {
    $('#moneyBody').innerHTML = '<div class="empty-note">No expenses yet. Try “Set a monthly budget of ₹30,000” or “I spent ₹450 on lunch”.</div>';
    return;
  }
  const pct = m.budget ? Math.min(100, Math.round(m.spent / m.budget * 100)) : 0;
  const cats = Object.entries(m.by_category).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const max = cats.length ? cats[0][1] : 1;
  $('#moneyBody').innerHTML = `
    <div class="money-stats"><div><small>Spent</small><strong>${inr(m.spent)}</strong></div><div><small>Budget</small><strong>${m.budget ? inr(m.budget) : '—'}</strong></div><div><small>Left</small><strong>${m.budget ? inr(m.budget - m.spent) : '—'}</strong></div></div>
    ${m.budget ? `<div class="progress-track money-bar"><span style="width:${pct}%${pct >= 100 ? ';background:linear-gradient(90deg,#e49a6c,#f0b38a)' : ''}"></span></div>` : ''}
    ${m.warnings.map(w => `<div class="warn-row">⚠ ${esc(w)}</div>`).join('')}
    ${cats.map(([c, v]) => `<div class="cat-row"><span>${esc(c.charAt(0).toUpperCase() + c.slice(1))}</span><i><b style="width:${Math.max(4, Math.round(v / max * 100))}%"></b></i><em>${inr(v)}</em></div>`).join('')}
    ${S.expenses.length ? `<h4 class="sub-head">Recent expenses</h4>${S.expenses.map((x, k) => `<div class="exp-row"><span>${esc(x.note || x.category)} <small>${esc(x.category)} · ${esc(x.date)}</small></span><em>${inr(x.amount)}</em><button class="del-btn" data-del-exp="${k}" aria-label="Delete expense" title="Delete">×</button></div>`).join('')}` : ''}
    <div class="money-actions">${m.spent ? '<button class="mini-link" data-reset-money>Reset spending to ₹0</button>' : ''}${m.budget || Object.keys(m.budgets).length ? '<button class="mini-link" data-clear-budget>Clear budget</button>' : ''}</div>`;
}

function renderReminders() {
  const open = S.reminders.filter(r => !r.done);
  $('#reminderList').innerHTML = open.length ? open.map(r => {
    const late = r.due < S.today;
    return `<article class="activity-item"><span class="activity-icon ${late ? 'act-late' : 'act-violet'}">${late ? '!' : '◷'}</span>
      <div class="grow"><p><strong>${esc(r.text)}</strong></p><time class="${late ? 'overdue' : ''}">${late ? 'Overdue · ' : 'Due '}${esc(dayLabel(r.due))}</time></div>
      <button class="del-btn" data-del-rem="${S.reminders.indexOf(r)}" aria-label="Delete reminder" title="Delete">×</button></article>`;
  }).join('') : '<div class="empty-note">No reminders. Try “Remind me to renew my passport by Dec 1”.</div>';
}

/* ---------- toast / sidebar / nav ---------- */
const sidebar = $('#sidebar');
$('#menuToggle').addEventListener('click', () => sidebar.classList.toggle('open'));
document.querySelectorAll('[data-view]').forEach(link => link.addEventListener('click', event => {
  const view = link.dataset.view;
  if (view === 'overview') return;
  event.preventDefault();
  if (view === 'memory') openMemory();
  else $(view === 'missions' ? '#missions' : '#calendar').scrollIntoView({ behavior: smooth, block: 'start' });
  if (link.classList.contains('nav-link')) document.querySelectorAll('.nav-link').forEach(i => i.classList.toggle('active', i.dataset.view === view));
  sidebar.classList.remove('open');
}));
document.querySelectorAll('[data-scroll]').forEach(link => link.addEventListener('click', () =>
  $(`#${link.dataset.scroll}`).scrollIntoView({ behavior: smooth, block: 'center' })));
$('#allMissions').addEventListener('click', openAllMissions);
$('#helpButton').addEventListener('click', () => showToast('Type a request in your own words. Anything that books, buys or sends waits for your approval.'));
$('#notificationsButton').addEventListener('click', () => S?.pending.length ? $('#approvals').scrollIntoView({ behavior: smooth, block: 'center' }) : showToast('You’re all caught up.'));
$('#profileButton').addEventListener('click', openMemory);
$('#dateButton').addEventListener('click', () => $('#calendar').scrollIntoView({ behavior: smooth, block: 'start' }));
const toggleCrew = () => { crewOpen = !crewOpen; if (S) renderCrew(); };
$('#agentsInfo').addEventListener('click', toggleCrew);
$('#crewButton').addEventListener('click', toggleCrew);

/* ---------- composer ---------- */
const commandForm = $('#commandForm');
const commandInput = $('#commandInput');
const panel = $('#responsePanel');

function setBusy(on) {
  busy = on;  // the button is never disabled: a disabled submit button also blocks Enter
  $('#sendButton').style.opacity = on ? .55 : '';
}

function renderResponse(j) {
  const running = j.status === 'running';
  const lines = j.log.map(l => `<div>${esc(l)}</div>`).join('');
  panel.hidden = false;
  panel.innerHTML = `
    <div class="response-head"><div><div class="eyebrow muted-eyebrow">${running ? 'WORKING ON IT' : j.status === 'done' ? 'ALL DONE' : 'SOMETHING WENT WRONG'}</div><p class="response-q">${esc(j.q)}</p></div>${running ? '<span class="spinner" aria-hidden="true"></span>' : '<button class="panel-menu" id="closeResponse" aria-label="Dismiss">×</button>'}</div>
    ${running ? `<div class="log-lines live">${lines}</div><p class="hint">Bigger requests can take 30–60 seconds while several agents work together.</p>`
      : `<div class="answer">${md(j.answer)}</div>${S?.pending.length ? '<p class="hint">Some actions are waiting for you in “Ready for your review”.</p>' : ''}<details class="run-log"><summary>Run log</summary><div class="log-lines">${lines}</div></details>`}`;
  const live = panel.querySelector('.live'); if (live) live.scrollTop = live.scrollHeight;
  $('#closeResponse')?.addEventListener('click', () => { panel.hidden = true; });
}

async function pollJob(id) {
  let tick = 0, note = '';
  const t0 = Date.now();
  for (;;) {
    let jb;
    try { jb = await api('/job/' + id); }
    catch (e) {
      if (/nahi mili/i.test(e.message)) { note = 'That request got lost (did the server restart?). Please send it again.'; break; }
      await sleep(2000); continue;
    }
    renderResponse(jb);
    if (tick++ % 3 === 0 && jb.status === 'running') refresh();
    if (jb.status !== 'running') break;
    if (Date.now() - t0 > 300000) { note = 'This is taking too long. You can send a new request.'; break; }
    await sleep(1200);
  }
  setBusy(false);
  await refresh();
  if (note) { showToast(note); return; }
  const last = await api('/job/' + id).catch(() => null);
  if (last) renderResponse(last);
  if (S?.pending.length) showToast('Waiting for your approval below.');
  panel.scrollIntoView({ behavior: smooth, block: 'nearest' });
}

async function submitCommand(value) {
  const q = value.trim();
  if (!q) { commandInput.focus(); return; }
  if (busy) { showToast('Still working on your last request. Give it a moment.'); commandFeedback.textContent = 'Still working on your last request…'; return; }
  setBusy(true);
  commandFeedback.textContent = '';
  try {
    const { id } = await api('/ask', { q });
    commandInput.value = '';
    renderResponse({ q, status: 'running', log: ['🧠 Starting…'] });
    panel.scrollIntoView({ behavior: smooth, block: 'nearest' });
    pollJob(id);
  } catch (e) { setBusy(false); showToast(e.message); }
}
const commandFeedback = $('#commandFeedback');
commandForm.addEventListener('submit', e => { e.preventDefault(); submitCommand(commandInput.value); });
commandInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); submitCommand(commandInput.value); }
});
document.querySelectorAll('[data-prompt]').forEach(b => b.addEventListener('click', () => {
  commandInput.value = b.dataset.prompt; commandInput.focus();
}));

const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
$('#voiceButton').addEventListener('click', () => {
  if (!SpeechRec) return showToast('Voice input works in Chrome or Edge.');
  const r = new SpeechRec(); r.lang = 'en-IN';
  r.onresult = e => { commandInput.value = e.results[0][0].transcript; commandInput.focus(); };
  r.onerror = () => showToast('Couldn’t hear that. Try again.');
  r.start(); showToast('Listening…');
});

/* ---------- approvals dialog ---------- */
const dialog = $('#reviewDialog');
let activeApproval = null;
const kv = rows => `<dl class="kv">${rows.filter(r => r[1] !== undefined && r[1] !== '').map(r => `<dt>${esc(r[0])}</dt><dd>${esc(r[1])}</dd>`).join('')}</dl>`;
function approvalBody(a) {
  const p = a.payload || {};
  if (a.kind === 'booking') return kv([['Booking', p.what], ['Details', p.details], ['Estimated cost', p.cost ? inr(p.cost) : '']]);
  if (a.kind === 'purchase') return kv([['Item', p.item], ['Price', p.price ? inr(p.price) : ''], ['Store', p.store]]);
  if (a.kind === 'send_message') return kv([['To', p.to], ['Subject', p.subject], ['Message', p.body]]);
  if (a.kind === 'delete_memory') return kv([['Forget this memory', p.key]]);
  return kv(Object.entries(p));
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-review]');
  if (!b) return;
  const a = S.pending.find(x => String(x.id) === b.dataset.review);
  if (!a) return;
  activeApproval = a;
  $('#dialogEyebrow').textContent = `REQUEST #${a.id} · ${agentLabel(a.agent).toUpperCase()}`;
  $('#dialogTitle').textContent = a.summary;
  $('#dialogBody').innerHTML = approvalBody(a);
  dialog.showModal();
});
async function decide(approve) {
  if (!activeApproval) return;
  const id = activeApproval.id;
  try {
    const { message } = await api('/approvals/' + id, { approve });
    dialog.close();
    showToast(message);
    refresh();
  } catch (e) { showToast(e.message); }
}
$('#dismissApproval').addEventListener('click', () => dialog.close());
$('#approveAction').addEventListener('click', () => decide(true));
$('#rejectAction').addEventListener('click', () => decide(false));
[dialog, $('#infoDialog')].forEach(d => d.addEventListener('click', e => { if (e.target === d) d.close(); }));

/* ---------- info dialog (agents, missions, memory) ---------- */
const info = $('#infoDialog');
function openInfo({ mark = '✧', eyebrow, title, html }) {
  $('#infoMark').textContent = mark; $('#infoEyebrow').textContent = eyebrow;
  $('#infoTitle').textContent = title; $('#infoBody').innerHTML = html;
  if (!info.open) info.showModal();
}
const chips = items => items.map(t => `<span class="chip">${esc(t)}</span>`).join('');

function openAgent(key) {
  const a = agentOf(key); if (!a) return;
  const status = { active: 'Recent', idle: 'Idle', paused: 'Paused' }[a.status];
  const last = a.last ? `Last run: ${a.last.ok ? '✅' : '❌'} ${a.last.sec.toFixed(1)}s` : a.key === 'chief' ? 'Plans and verifies every request' : 'Ready';
  openInfo({
    mark: a.glyph, eyebrow: `AGENT · ${status.toUpperCase()}`, title: a.name,
    html: `<p>${esc(a.role)}</p><p class="faint">${esc(last)}</p>
      <h4>Tools</h4><div>${chips(a.tools)}</div>
      <h4>Permissions</h4><ul>${a.perms.map(p => `<li>✓ ${esc(p)}</li>`).join('')}</ul>
      <h4>Security boundaries</h4><p class="faint">Payments, bookings and messages need your approval. Sensitive data (passwords, card numbers) is never stored.</p>
      ${a.history.length ? `<h4>Approval history</h4><ul>${a.history.map(h => `<li>${esc(h)}</li>`).join('')}</ul>` : ''}
      ${a.key !== 'chief' ? `<div class="dialog-actions"><button class="button-secondary" data-pause="${esc(a.key)}" data-to="${a.status !== 'paused'}">${a.status === 'paused' ? '▶ Resume agent' : '⏸ Pause agent'}</button></div>` : ''}`
  });
}
function missionDetail(j) {
  return `<h4>Request</h4><p>${esc(j.q)}</p><h4>${j.status === 'running' ? 'Progress' : 'Answer'}</h4>
    ${j.status === 'running' ? '<p class="faint">Still working. Progress is shown under the composer.</p>' : `<div class="answer">${md(j.answer)}</div>`}
    <h4>Run log</h4><div class="log-lines">${j.log.map(l => `<div>${esc(l)}</div>`).join('')}</div>`;
}
function openAllMissions() {
  openInfo({ eyebrow: 'MISSIONS', title: 'All missions', html: S.jobs.map(j => missionHTML(j)).join('') || '<div class="empty-note">No missions yet.</div>' });
}
function openMemory() {
  const mem = Object.entries(S.memory), lists = Object.entries(S.lists);
  openInfo({
    mark: '◉', eyebrow: 'YOURS TO CONTROL', title: 'My memory',
    html: `<h4>What Ysoriel remembers</h4>${mem.length ? mem.map(([k, v]) => `<div class="mem-row"><div><strong>${esc(k)}</strong><span>${esc(v)}</span></div><button class="del-btn" data-del-mem="${esc(k)}" aria-label="Delete ${esc(k)}" title="Delete">×</button></div>`).join('') : '<p class="faint">Nothing saved yet. Tell Ysoriel “remember that I prefer window seats”.</p>'}
      ${lists.length ? `<h4>Lists</h4>${lists.map(([n, items]) => `<div class="mem-row"><div><strong>${esc(n)}</strong><span>${items.length ? items.map(it => `<span class="chip">${esc(it)} <button class="chip-x" data-del-item="${esc(n)}" data-item="${esc(it)}" aria-label="Remove ${esc(it)}">×</button></span>`).join('') : '<em class="faint">empty</em>'}</span></div><button class="del-btn" data-del-list="${esc(n)}" aria-label="Delete list ${esc(n)}" title="Delete whole list">×</button></div>`).join('')}` : ''}
      ${S.drafts.length ? `<h4>Drafts</h4>${S.drafts.map(d => `<div class="mem-row"><div><strong>To ${esc(d.to)}: ${esc(d.subject)}</strong><span class="pre">${esc(d.body)}</span></div><button class="del-btn" data-del-draft="${d.i}" aria-label="Delete draft" title="Delete">×</button></div>`).join('')}` : ''}
      <p class="faint">Deleting here is instant. If you ask Ysoriel to forget something in chat, it asks for your approval first.</p>`
  });
}
document.addEventListener('click', async e => {
  const row = e.target.closest('[data-agent]');
  if (row) { sidebar.classList.remove('open'); return openAgent(row.dataset.agent); }
  const job = e.target.closest('[data-job]');
  if (job) { const j = S.jobs.find(x => x.id === job.dataset.job); if (j) openInfo({ eyebrow: 'MISSION', title: 'Mission details', html: missionDetail(j) }); return; }
  const pause = e.target.closest('[data-pause]');
  if (pause) {
    try {
      await api(`/agents/${pause.dataset.pause}/pause`, { paused: pause.dataset.to === 'true' });
      info.close(); await refresh(); showToast(pause.dataset.to === 'true' ? 'Agent paused.' : 'Agent resumed.');
    } catch (err) { showToast(err.message); }
  }
});

/* ---------- delete / reset (direct edits) ---------- */
async function edit(path, payload, reopenMemory) {
  try {
    const r = await api(path, payload);
    showToast(r.message || 'Done');
    await refresh();
    if (reopenMemory) openMemory();
  } catch (err) { showToast(err.message); }
}
document.addEventListener('click', e => {
  const q = sel => e.target.closest(sel);
  let b;
  if ((b = q('[data-del-event]'))) { const ev = S.events[+b.dataset.delEvent]; if (ev) edit('/events/delete', { title: ev.title, date: ev.date, start: ev.start }); }
  else if ((b = q('[data-clear-day]'))) { if (confirm(`Remove every event on ${dayLabel(b.dataset.clearDay)}?`)) edit('/events/clear_day', { date: b.dataset.clearDay }); }
  else if ((b = q('[data-del-rem]'))) { const r = S.reminders[+b.dataset.delRem]; if (r) edit('/reminders/delete', { text: r.text, due: r.due }); }
  else if ((b = q('[data-del-exp]'))) { const x = S.expenses[+b.dataset.delExp]; if (x) edit('/expenses/delete', { i: x.i, amount: x.amount, category: x.category }); }
  else if (q('[data-reset-money]')) { if (confirm('Reset spending to ₹0? This removes every recorded expense.')) edit('/money/reset', { expenses: true }); }
  else if (q('[data-clear-budget]')) { if (confirm('Clear all budgets?')) edit('/money/reset', { budgets: true }); }
  else if ((b = q('[data-del-mem]'))) edit('/memory/delete', { key: b.dataset.delMem }, true);
  else if ((b = q('[data-del-item]'))) edit('/lists/delete', { list: b.dataset.delItem, item: b.dataset.item }, true);
  else if ((b = q('[data-del-list]'))) { if (confirm(`Delete the whole “${b.dataset.delList}” list?`)) edit('/lists/delete', { list: b.dataset.delList }, true); }
  else if ((b = q('[data-del-draft]'))) { const d = S.drafts.find(x => x.i === +b.dataset.delDraft); if (d) edit('/drafts/delete', { i: d.i, subject: d.subject }, true); }
  else if (q('#togglePast')) { showPast = !showPast; renderAgenda(); }
});

/* ---------- boot ---------- */
(async () => {
  await refresh();
  if (S?.running) { setBusy(true); pollJob(S.running); }
  setInterval(() => { if (!busy && !document.hidden) refresh(); }, 20000);
})();
