const API = '';
const EVENT_TYPES = ['model.resolved','run.started','run.attempt_failed','node.started','node.completed','tool.started','tool.completed','rag.started','rag.completed','subagent.started','subagent.completed','approval.required','checkpoint.created','run.completed','run.failed','run.cancelled'];
const titles = {runs:'运行工作台',approvals:'人工审批',knowledge:'知识检索',memory:'长期记忆',graph:'图结构'};

const app = {
  runs: [], currentRun: null, source: null, graphs: [], models: [],

  async init() {
    document.querySelectorAll('.nav-item').forEach(button => button.addEventListener('click', () => this.navigate(button.dataset.page)));
    document.querySelector('#new-run-button').addEventListener('click', () => document.querySelector('#run-dialog').showModal());
    document.querySelector('#refresh-runs').addEventListener('click', () => this.loadRuns());
    document.querySelector('#cancel-run').addEventListener('click', () => this.cancelCurrentRun());
    document.querySelector('#load-approvals').addEventListener('click', () => this.loadApprovals());
    document.querySelector('#run-form').addEventListener('submit', event => this.createRun(event));
    document.querySelector('#kb-form').addEventListener('submit', event => this.createKnowledgeBase(event));
    document.querySelector('#doc-form').addEventListener('submit', event => this.ingestDocument(event));
    document.querySelector('#rag-form').addEventListener('submit', event => this.searchKnowledge(event));
    document.querySelector('#memory-add-form').addEventListener('submit', event => this.addMemory(event));
    document.querySelector('#memory-search-form').addEventListener('submit', event => this.searchMemory(event));
    document.querySelector('#graph-select').addEventListener('change', event => this.loadGraph(event.target.value));
    document.querySelector('#policy-mode').addEventListener('change', event => this.togglePolicyMode(event.target.value));
    document.querySelector('#policy-model').addEventListener('change', () => this.updatePolicyHint());
    document.addEventListener('keydown', event => {
      if (event.key.toLowerCase() === 'n' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) document.querySelector('#run-dialog').showModal();
    });
    await Promise.all([this.checkHealth(), this.loadGraphs(), this.loadRuns(), this.loadModels()]);
  },

  navigate(page) {
    document.querySelectorAll('.page').forEach(el => el.classList.toggle('active', el.id === `page-${page}`));
    document.querySelectorAll('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.page === page));
    document.querySelector('#page-title').textContent = titles[page] || 'Runtime Atlas';
    if (page === 'graph' && this.graphs.length) this.loadGraph(document.querySelector('#graph-select').value || this.graphs[0]);
    if (page === 'approvals' && this.currentRun) document.querySelector('#approval-run-id').value = this.currentRun.run_id;
  },

  async request(path, options = {}) {
    const response = await fetch(`${API}${path}`, options);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
    return body;
  },

  async checkHealth() {
    try { await this.request('/health'); document.querySelector('#health-dot').classList.add('ok'); document.querySelector('#health-label').textContent = 'API 在线'; }
    catch { document.querySelector('#health-label').textContent = 'API 不可用'; }
  },

  async loadGraphs() {
    try {
      const data = await this.request('/graphs'); this.graphs = data.graphs;
      ['#run-graph-select','#graph-select'].forEach(selector => document.querySelector(selector).innerHTML = this.graphs.map(name => `<option>${this.escape(name)}</option>`).join(''));
    } catch (error) { this.toast(`图目录读取失败：${error.message}`, true); }
  },

  togglePolicyMode(mode) {
    document.querySelector('#policy-tier-wrap').hidden = mode !== 'tier';
    document.querySelector('#policy-model-wrap').hidden = mode !== 'specific';
    if (mode === 'specific') this.updatePolicyHint();
  },

  async loadModels() {
    try {
      const data = await this.request('/models'); this.models = data.models;
      const select = document.querySelector('#policy-model');
      select.innerHTML = this.models.map(model => `<option value="${this.escape(model.catalog_id)}">${this.escape(model.display_name)}</option>`).join('');
      const hint = document.querySelector('#policy-hint');
      if (data.stale) { hint.textContent = '模型目录已过期（stale），以下选择可能不可用。'; hint.classList.add('warn'); }
      else { hint.classList.remove('warn'); this.updatePolicyHint(); }
    } catch {
      const hint = document.querySelector('#policy-hint');
      hint.textContent = '模型目录不可用（LiteLLM 未启动？），仍可用 auto 策略创建。'; hint.classList.add('warn');
    }
  },

  updatePolicyHint() {
    const model = this.models.find(entry => entry.catalog_id === document.querySelector('#policy-model').value);
    document.querySelector('#policy-hint').textContent = model
      ? `${model.catalog_id} · 能力：${model.capabilities.join(' / ')} · 创建时冻结，恢复与重试沿用同一模型`
      : '创建时解析并冻结进 Run，恢复与重试沿用同一模型。';
  },

  async loadRuns(selectId = null) {
    try {
      this.runs = await this.request('/runs?limit=100'); this.renderRunMetrics(); this.renderRunList();
      const target = selectId || this.currentRun?.run_id;
      if (target && this.runs.some(run => run.run_id === target)) this.showRun(target, false);
    } catch (error) { document.querySelector('#run-list').innerHTML = `<div class="empty">无法读取 Run：${this.escape(error.message)}</div>`; }
  },

  renderRunMetrics() {
    const terminal = this.runs.filter(r => ['completed','failed','cancelled'].includes(r.status));
    const completed = this.runs.filter(r => r.status === 'completed').length;
    document.querySelector('#metric-all').textContent = this.runs.length;
    document.querySelector('#metric-active').textContent = this.runs.filter(r => ['queued','running'].includes(r.status)).length;
    document.querySelector('#metric-paused').textContent = this.runs.filter(r => r.status === 'paused').length;
    document.querySelector('#metric-rate').textContent = terminal.length ? `${Math.round(completed / terminal.length * 100)}%` : '—';
  },

  renderRunList() {
    const list = document.querySelector('#run-list');
    if (!this.runs.length) { list.innerHTML = '<div class="empty">还没有 Run。按 N 将第一个请求加入队列。</div>'; return; }
    list.innerHTML = this.runs.map(run => `<button class="run-row ${run.run_id === this.currentRun?.run_id ? 'active' : ''}" data-run-id="${this.escape(run.run_id)}"><strong>${this.escape(run.run_id.slice(0,8))}</strong><span class="badge ${run.status}">${this.escape(run.status)}</span><p>${this.escape(run.input_text)}</p><span class="run-meta"><span>${this.escape(run.graph_name)}</span><time>${this.time(run.created_at)}</time></span></button>`).join('');
    list.querySelectorAll('.run-row').forEach(row => row.addEventListener('click', () => this.showRun(row.dataset.runId)));
  },

  async createRun(event) {
    event.preventDefault();
    const form = event.currentTarget; const submitter = event.submitter;
    if (submitter?.value === 'cancel') { document.querySelector('#run-dialog').close(); return; }
    const data = Object.fromEntries(new FormData(form));
    const body = { session_id: data.session_id, graph_name: data.graph_name, input_text: data.input_text };
    if (data.policy_mode === 'specific') body.model_policy = { mode: 'specific', model_id: data.policy_model };
    else if (data.policy_mode === 'tier') body.model_policy = { mode: 'tier', tier: data.policy_tier };
    else body.model_policy = { mode: 'auto' };
    try {
      const run = await this.request('/runs', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      document.querySelector('#run-dialog').close(); this.toast('Run 已加入 PostgreSQL 队列'); this.navigate('runs'); await this.loadRuns(run.run_id); this.showRun(run.run_id);
    } catch (error) { this.toast(`创建失败：${error.message}`, true); }
  },

  async showRun(runId, reconnect = true) {
    try {
      const run = await this.request(`/runs/${encodeURIComponent(runId)}`); this.currentRun = run; this.renderRunList();
      document.querySelector('#run-detail-empty').hidden = true; document.querySelector('#run-detail').hidden = false;
      document.querySelector('#detail-title').textContent = `Run ${run.run_id.slice(0,8)}`;
      const facts = [['状态',run.status],['图',run.graph_name],['Session 输入',run.input_text],['终止原因',run.termination_reason || '—']];
      if (run.model_decision) {
        const decision = run.model_decision;
        facts.push(['模型', `${decision.resolved_model}${decision.resolved_tier ? ` (${decision.resolved_tier})` : ''}`]);
        facts.push(['选择依据', `${decision.reason} · 目录 ${String(decision.catalog_version).slice(0,8)}`]);
      }
      document.querySelector('#run-facts').innerHTML = facts.map(([k,v]) => `<div><dt>${this.escape(k)}</dt><dd>${this.escape(v)}</dd></div>`).join('');
      document.querySelector('#run-output').textContent = run.output_text || (run.error ? `ERROR · ${run.error}` : '等待 Supervisor 完成…');
      document.querySelector('#cancel-run').hidden = ['completed','failed','cancelled'].includes(run.status);
      if (reconnect) this.connectEvents(runId);
    } catch (error) { this.toast(`Run 读取失败：${error.message}`, true); }
  },

  connectEvents(runId) {
    this.source?.close(); const track = document.querySelector('#event-track'); track.innerHTML = '';
    document.querySelector('#stream-state').textContent = '正在连接';
    const source = new EventSource(`/runs/${encodeURIComponent(runId)}/stream`); this.source = source;
    const receive = event => { const data = JSON.parse(event.data); this.appendEvent(data); if (['run.completed','run.failed','run.cancelled'].includes(data.type)) { source.close(); document.querySelector('#stream-state').textContent = '终态'; this.loadRuns(runId); } };
    EVENT_TYPES.forEach(type => source.addEventListener(type, receive));
    source.onopen = () => document.querySelector('#stream-state').textContent = '实时连接';
    source.onerror = () => { if (source.readyState === EventSource.CLOSED) document.querySelector('#stream-state').textContent = '连接结束'; };
  },

  appendEvent(data) {
    const item = document.createElement('li'); item.className = `event-item ${data.type.startsWith('run.') && data.type !== 'run.started' ? 'terminal' : ''}`;
    const header = document.createElement('header'); const seq = document.createElement('code'); seq.textContent = `#${data.seq}`; const type = document.createElement('b'); type.textContent = data.type; header.append(seq,type);
    const payload = document.createElement('p'); payload.textContent = [data.node ? `node=${data.node}` : '', Object.keys(data.payload || {}).length ? JSON.stringify(data.payload) : ''].filter(Boolean).join(' · ') || '—'; item.append(header,payload);
    document.querySelector('#event-track').appendChild(item); item.scrollIntoView({block:'nearest'});
  },

  async cancelCurrentRun() { if (!this.currentRun) return; try { await this.request(`/runs/${this.currentRun.run_id}/cancel`,{method:'POST'}); this.toast('Run 已取消'); await this.loadRuns(this.currentRun.run_id); } catch(error){ this.toast(`取消失败：${error.message}`,true); } },

  async loadApprovals() {
    const runId = document.querySelector('#approval-run-id').value.trim(); if (!runId) return this.toast('先输入 Run ID',true);
    try { const rows = await this.request(`/approvals/run/${encodeURIComponent(runId)}`); this.renderApprovals(rows); } catch(error){ this.toast(`审批读取失败：${error.message}`,true); }
  },

  renderApprovals(rows) {
    const target = document.querySelector('#approval-list'); if (!rows.length) { target.innerHTML = '<div class="empty">这个 Run 没有审批记录。</div>'; return; }
    target.innerHTML = rows.map(row => `<article class="approval-card"><div><p class="kicker">${this.escape(row.tool_name || row.action)}</p><h3>${this.escape(row.action)} · <span class="badge ${row.status}">${row.status}</span></h3><pre>${this.escape(JSON.stringify(row.canonical_arguments || row.details,null,2))}</pre><small>hash ${this.escape(row.arguments_hash || '—')}</small></div><div class="approval-actions">${row.status === 'pending' ? `<button class="primary approval-resolve" data-id="${row.id}" data-decision="approve">批准</button><button class="danger-quiet approval-resolve" data-id="${row.id}" data-decision="reject">拒绝</button>` : ''}</div></article>`).join('');
    target.querySelectorAll('.approval-resolve').forEach(button => button.addEventListener('click', () => this.resolveApproval(button.dataset.id,button.dataset.decision)));
  },

  async resolveApproval(id, decision) { try { await this.request(`/approvals/${id}/${decision}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({resolved_by:'runtime-atlas-ui'})}); this.toast(decision === 'approve' ? '已批准并重新入队' : '已拒绝并重新入队'); this.loadApprovals(); } catch(error){ this.toast(`审批失败：${error.message}`,true); } },

  async createKnowledgeBase(event) { event.preventDefault(); const data=Object.fromEntries(new FormData(event.currentTarget)); try { const row=await this.request('/knowledge-bases',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}); document.querySelector('#kb-result').textContent=`ID ${row.id}`; document.querySelectorAll('[name="knowledge_base_id"]').forEach(input=>input.value=row.id); this.toast('知识库已创建'); } catch(error){ this.toast(error.message,true); } },
  async ingestDocument(event) { event.preventDefault(); const data=Object.fromEntries(new FormData(event.currentTarget)); const id=data.knowledge_base_id; delete data.knowledge_base_id; try { const row=await this.request(`/knowledge-bases/${id}/documents`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...data,metadata:{source:'runtime-atlas-ui'}})}); document.querySelector('#doc-result').textContent=`${row.status} · ${row.chunk_count} chunks`; this.toast('文档已向量化入库'); } catch(error){ this.toast(error.message,true); } },
  async searchKnowledge(event) { event.preventDefault(); const data=Object.fromEntries(new FormData(event.currentTarget)); const id=data.knowledge_base_id; try { const row=await this.request(`/knowledge-bases/${id}/search`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:data.query,top_k:5})}); document.querySelector('#rag-result').innerHTML=this.resultCards(row.chunks.map(x=>({text:x.content,score:x.score,metadata:x.metadata}))); } catch(error){ this.toast(error.message,true); } },

  async addMemory(event) { event.preventDefault(); const data=Object.fromEntries(new FormData(event.currentTarget)); try { const row=await this.request(`/memory/${encodeURIComponent(data.user_id)}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:[{role:'user',content:data.content}],metadata:{source:'runtime-atlas-ui'}})}); this.renderMemory(row.memories); this.toast('对话已交给 Mem0'); } catch(error){ this.toast(error.message,true); } },
  async searchMemory(event) { event.preventDefault(); const data=Object.fromEntries(new FormData(event.currentTarget)); try { const row=await this.request(`/memory/${encodeURIComponent(data.user_id)}/search`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:data.query,top_k:8})}); this.renderMemory(row.memories); } catch(error){ this.toast(error.message,true); } },
  renderMemory(rows){ document.querySelector('#memory-results').innerHTML=this.resultCards(rows); },
  resultCards(rows){ return rows.length ? rows.map(row=>`<div class="result-card"><b>${row.score == null ? 'MEMORY' : `SCORE ${Number(row.score).toFixed(3)}`}</b><p>${this.escape(row.text || '')}</p><small>${this.escape(JSON.stringify(row.metadata || {}))}</small></div>`).join('') : '<div class="empty">没有匹配结果。</div>'; },

  async loadGraph(name) { try { const graph=await this.request(`/graphs/${encodeURIComponent(name)}`); this.drawGraph(graph); } catch(error){ this.toast(`图读取失败：${error.message}`,true); } },
  drawGraph(graph) {
    const svg=document.querySelector('#graph-svg'); svg.innerHTML=''; const ns='http://www.w3.org/2000/svg';
    const defs=document.createElementNS(ns,'defs'); defs.innerHTML='<marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#8faeba"/></marker>'; svg.appendChild(defs);
    const depth={}; depth[graph.entry]=0; let changed=true; while(changed){ changed=false; graph.edges.forEach(edge=>{ if(depth[edge.source]!==undefined && depth[edge.target]===undefined){depth[edge.target]=depth[edge.source]+1;changed=true;} }); }
    const groups={}; graph.nodes.forEach(node=>{ const d=depth[node.id]??2; (groups[d]??=[]).push(node); }); const positions={}; Object.entries(groups).forEach(([d,nodes])=>nodes.forEach((node,i)=>positions[node.id]={x:70+Number(d)*240,y:70+i*(430/Math.max(nodes.length,1))}));
    graph.edges.forEach(edge=>this.drawEdge(svg,positions[edge.source],positions[edge.target],false)); const supervisor=graph.nodes.find(n=>n.type==='supervisor'); graph.nodes.filter(n=>['tool','rag','subagent','approval'].includes(n.type)).forEach(node=>this.drawEdge(svg,positions[node.id],positions[supervisor?.id],true));
    graph.nodes.forEach(node=>{ const p=positions[node.id]; const g=document.createElementNS(ns,'g'); g.setAttribute('class',`graph-node ${node.type}`); g.setAttribute('transform',`translate(${p.x} ${p.y})`); const rect=document.createElementNS(ns,'rect'); rect.setAttribute('width','150');rect.setAttribute('height','54'); const type=document.createElementNS(ns,'text');type.setAttribute('x','12');type.setAttribute('y','17');type.setAttribute('class','node-type');type.textContent=node.type.toUpperCase(); const label=document.createElementNS(ns,'text');label.setAttribute('x','12');label.setAttribute('y','38');label.textContent=node.id; g.append(rect,type,label);g.addEventListener('click',()=>document.querySelector('#graph-inspector').textContent=`${node.id}\n\nTYPE\n${node.type}\n\nPROMPT\n${node.prompt||'—'}\n\nCONFIG\n${JSON.stringify(node.config,null,2)}`);svg.appendChild(g); });
    svg.setAttribute('viewBox','0 0 850 560');
  },
  drawEdge(svg,a,b,isReturn){ if(!a||!b)return; const ns='http://www.w3.org/2000/svg';const path=document.createElementNS(ns,'path'); const sx=isReturn?a.x:a.x+150, sy=a.y+27, tx=isReturn?b.x+150:b.x, ty=b.y+27; const bend=(sx+tx)/2;path.setAttribute('d',`M${sx},${sy} C${bend},${sy} ${bend},${ty} ${tx},${ty}`);path.setAttribute('class',`graph-edge ${isReturn?'return':''}`);svg.appendChild(path); },

  escape(value){ const div=document.createElement('div');div.textContent=String(value??'');return div.innerHTML; },
  time(value){ return value ? new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value)) : '—'; },
  toast(message,error=false){ const el=document.querySelector('#toast');el.textContent=message;el.className=error?'show error':'show';clearTimeout(this.toastTimer);this.toastTimer=setTimeout(()=>el.className='',3200); }
};

document.addEventListener('DOMContentLoaded',()=>app.init());
