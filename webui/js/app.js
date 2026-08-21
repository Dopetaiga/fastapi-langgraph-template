const API = 'http://localhost:8000';

const fmtDateTime = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
});

const app = {
  runs: [],
  currentRunId: null,
  eventSource: null,

  init() {
    document.querySelectorAll('.nav a').forEach(a => {
      a.addEventListener('click', e => {
        e.preventDefault();
        this.navigate(a.dataset.page);
        document.querySelectorAll('.nav li').forEach(li => li.classList.remove('active'));
        a.parentElement.classList.add('active');
      });
      a.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          a.click();
        }
      });
    });
    this.loadRuns();
  },

  navigate(page) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const el = document.getElementById('page-' + page);
    if (el) el.classList.add('active');
    if (page === 'runs') this.loadRuns();
    if (page === 'approvals') document.getElementById('apr-run-id').value = this.currentRunId || '';
  },

  // === Runs ===
  async createRun() {
    this.navigate('create-run');
  },

  async submitCreateRun() {
    const session = document.getElementById('cr-session').value;
    const graph = document.getElementById('cr-graph').value;
    const input = document.getElementById('cr-input').value;
    if (!input.trim()) return this.toast('请输入输入文本', 'error');

    try {
      const resp = await fetch(`${API}/runs`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({session_id: session, graph_name: graph, input_text: input})
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const run = await resp.json();
      this.toast(`Run 已创建: ${run.run_id}`, 'success');
      await this.executeRun(run.run_id);
    } catch (e) {
      this.toast('创建失败: ' + e.message, 'error');
    }
  },

  async executeRun(runId) {
    try {
      const resp = await fetch(`${API}/runs/${runId}/execute`, {method: 'POST'});
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const result = await resp.json();
      this.toast(`Run 完成: ${result.termination_reason}`, 'success');
      this.loadRuns();
      this.showRunDetail(runId);
    } catch (e) {
      this.toast('执行失败: ' + e.message, 'error');
    }
  },

  async loadRuns() {
    try {
      const tbody = document.getElementById('runs-table-body');
      if (this.runs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">暂无数据，点击「新建 Run」开始</td></tr>';
      } else {
        tbody.innerHTML = this.runs.map(r => `
          <tr>
            <td><code>${r.run_id.slice(0,8)}</code></td>
            <td>${r.graph_name}</td>
            <td>${this.esc(r.input_text)}</td>
            <td><span class="badge badge-${r.status}">${r.status}</span></td>
            <td>${r.created_at ? fmtDateTime.format(new Date(r.created_at)) : '-'}</td>
            <td>
              <button class="btn btn-sm btn-primary" onclick="app.showRunDetail('${r.run_id}')">查看</button>
            </td>
          </tr>
        `).join('');
      }
    } catch (e) {
      this.toast('加载失败: ' + e.message, 'error');
    }
  },

  showRunDetail(runId) {
    this.currentRunId = runId;
    this.navigate('run-detail');
    document.getElementById('run-info').innerHTML = `
      <div class="run-info-item"><div class="run-info-label">Run ID</div><div class="run-info-value"><code>${runId}</code></div></div>
    `;
    document.getElementById('event-stream').innerHTML = '<div class="empty">连接事件流…</div>';
    this.connectStream(runId);
  },

  connectStream(runId) {
    if (this.eventSource) this.eventSource.close();
    this.eventSource = new EventSource(`${API}/runs/${runId}/stream?after_seq=-1`);
    const streamEl = document.getElementById('event-stream');
    streamEl.innerHTML = '';

    this.eventSource.onmessage = (e) => {
      const data = JSON.parse(e.data);
      const item = document.createElement('div');
      item.className = `event-item event-${data.type.replace('.', '-')}`;
      item.innerHTML = `<span class="event-seq">#${data.seq}</span><span class="event-type">${this.esc(data.type)}</span><span class="event-payload">${this.esc(JSON.stringify(data.payload))}</span>`;
      streamEl.appendChild(item);
      streamEl.scrollTop = streamEl.scrollHeight;
      if (data.type === 'run.completed' || data.type === 'run.failed') {
        this.eventSource.close();
      }
    };
    this.eventSource.onerror = () => {
      streamEl.innerHTML += '<div class="empty" style="color:var(--red)">连接断开</div>';
    };
  },

  // === Approvals ===
  async loadApprovals() {
    const runId = document.getElementById('apr-run-id').value;
    if (!runId) return this.toast('请输入 Run ID', 'error');
    try {
      const resp = await fetch(`${API}/approvals/run/${runId}`);
      const approvals = await resp.json();
      const tbody = document.getElementById('approvals-table');
      if (approvals.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">该 Run 无待审批</td></tr>';
        return;
      }
      tbody.innerHTML = approvals.map(a => `
        <tr>
          <td><code>${a.id.slice(0,8)}</code></td>
          <td>${a.run_id.slice(0,8)}</td>
          <td>${this.esc(a.action)}</td>
          <td><span class="badge badge-${a.status}">${a.status}</span></td>
          <td>${a.created_at ? fmtDateTime.format(new Date(a.created_at)) : '-'}</td>
          <td>
            ${a.status === 'pending' ? `
              <button class="btn btn-sm btn-primary" onclick="app.approve('${a.id}')">批准</button>
              <button class="btn btn-sm btn-danger" onclick="app.reject('${a.id}')">拒绝</button>
            ` : '-'}
          </td>
        </tr>
      `).join('');
    } catch (e) {
      this.toast('加载失败: ' + e.message, 'error');
    }
  },

  async approve(id) {
    await this._resolveApproval(id, 'approve');
  },
  async reject(id) {
    await this._resolveApproval(id, 'reject');
  },
  async _resolveApproval(id, action) {
    const body = {resolved_by: 'webui'};
    try {
      const resp = await fetch(`${API}/approvals/${id}/${action}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      this.toast(`审批已${action === 'approve' ? '批准' : '拒绝'}`, 'success');
      this.loadApprovals();
    } catch (e) {
      this.toast('操作失败: ' + e.message, 'error');
    }
  },

  // === Memory ===
  switchMemoryTab(tab) {
    document.querySelectorAll('.memory-panel').forEach(p => p.style.display = 'none');
    document.getElementById('memory-' + tab).style.display = 'block';
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    // Use event delegation target or this function's caller context
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(t => {
      if (t.getAttribute('onclick')?.includes(tab)) t.classList.add('active');
    });
  },

  async putUserMemory() {
    const body = {
      user_id: document.getElementById('mem-user-id').value,
      key: document.getElementById('mem-user-key').value,
      value: JSON.parse(document.getElementById('mem-user-value').value || '{}'),
    };
    try {
      const resp = await fetch(`${API}/memory/user`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      this.toast('用户记忆已存储', 'success');
      this.loadUserMemory();
    } catch (e) {
      this.toast('存储失败: ' + e.message, 'error');
    }
  },

  async loadUserMemory() {
    const userId = document.getElementById('mem-user-id').value;
    try {
      const resp = await fetch(`${API}/memory/user/${userId}`);
      const data = await resp.json();
      const tbody = document.getElementById('user-memory-table');
      tbody.innerHTML = data.map(f => `
        <tr><td>${f.user_id}</td><td>${f.key}</td><td>${this.esc(JSON.stringify(f.value))}</td><td>${f.namespace}</td></tr>
      `).join('') || '<tr><td colspan="4" class="empty">无数据</td></tr>';
    } catch (e) {
      this.toast('加载失败: ' + e.message, 'error');
    }
  },

  async putTeamMemory() {
    const body = {
      team_id: document.getElementById('mem-team-id').value,
      key: document.getElementById('mem-team-key').value,
      value: JSON.parse(document.getElementById('mem-team-value').value || '{}'),
    };
    try {
      const resp = await fetch(`${API}/memory/team`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      this.toast('团队记忆已存储', 'success');
      this.loadTeamMemory();
    } catch (e) {
      this.toast('存储失败: ' + e.message, 'error');
    }
  },

  async loadTeamMemory() {
    const teamId = document.getElementById('mem-team-id').value;
    try {
      const resp = await fetch(`${API}/memory/team/${teamId}`);
      const data = await resp.json();
      const tbody = document.getElementById('team-memory-table');
      tbody.innerHTML = data.map(f => `
        <tr><td>${f.team_id || f.user_id}</td><td>${f.key}</td><td>${this.esc(JSON.stringify(f.value))}</td></tr>
      `).join('') || '<tr><td colspan="3" class="empty">无数据</td></tr>';
    } catch (e) {
      this.toast('加载失败: ' + e.message, 'error');
    }
  },

  // === Worker ===
  async runWorker() {
    this.toast('Worker 已在后台运行 (run_forever)', 'success');
  },

  // === Utils ===
  esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  },

  toast(msg, type = 'success') {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = `toast ${type} show`;
    setTimeout(() => el.classList.remove('show'), 3000);
  },
};

document.addEventListener('DOMContentLoaded', () => app.init());
