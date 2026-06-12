import { useState, useEffect, useRef, useCallback } from 'react';
import './index.css';
import Sidebar from './components/Sidebar';
import GoalPanel from './components/GoalPanel';
import KnowledgePanel from './components/KnowledgePanel';
import ExperimentDashboard from './components/ExperimentDashboard';
import ResultsPanel from './components/ResultsPanel';
import DecisionPanel from './components/DecisionPanel';
import PapersView from './components/PapersView';
import ExperimentsPanel from './components/ExperimentsPanel';
import ChatPanel from './components/ChatPanel';
import SettingsPanel from './components/SettingsPanel';

const API_BASE = 'http://localhost:8000';

export default function App() {
  // Chat is the primary view — default just like Claude
  const [activeNav, setActiveNav] = useState('chat');
  const [selectedExp, setSelectedExp] = useState(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => localStorage.getItem('sidebar-collapsed') === 'true'
  );

  const handleToggleCollapse = useCallback(() => {
    setSidebarCollapsed(prev => {
      const next = !prev;
      localStorage.setItem('sidebar-collapsed', String(next));
      return next;
    });
  }, []);

  const [counts, setCounts] = useState({ documents: 0, tds: 0, papers: 0, experiments: 0, qdrant_parsed: 0 });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [loopState, setLoopState] = useState(null);
  const [loopLoading, setLoopLoading] = useState(false);
  const loopLoadingRef = useRef(false);

  // ── Session state (lifted from ChatPanel so Sidebar can drive it) ──────────
  const [sessionId, setSessionId] = useState('default');
  const [sessions, setSessions] = useState([]);

  // ── Polling ────────────────────────────────────────────────────────────────

  useEffect(() => {
    fetchStats();
    fetchLoopStatus();
    fetchSessions();
    const statsInterval = setInterval(fetchStats, 30000);
    const loopInterval  = setInterval(fetchLoopStatus, 10000);
    return () => {
      clearInterval(statsInterval);
      clearInterval(loopInterval);
    };
  }, []);

  const fetchStats = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/stats`);
      if (res.ok) setCounts(await res.json());
    } catch (_) {}
  };

  const fetchLoopStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/loop/status`);
      if (res.ok) setLoopState(await res.json());
    } catch (_) {}
  };

  const fetchSessions = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/chat/sessions`);
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions || []);
      }
    } catch (_) {}
  };

  // ── Session handlers ───────────────────────────────────────────────────────

  const handleNewSession = useCallback(() => {
    const newId = 'session-' + Date.now();
    setSessionId(newId);
    setActiveNav('chat');
    // Fetch after a short delay to let backend register it
    setTimeout(fetchSessions, 400);
  }, []);

  const handleSessionChange = useCallback((sid) => {
    setSessionId(sid);
    setActiveNav('chat');
  }, []);

  const handleDeleteSession = useCallback(async (sid, e) => {
    e?.stopPropagation();
    if (!confirm('Delete this session?')) return;
    try {
      await fetch(`${API_BASE}/api/chat/sessions/${encodeURIComponent(sid)}`, { method: 'DELETE' });
      setSessions(prev => {
        const remaining = prev.filter(s => s.session_id !== sid);
        if (sid === sessionId) {
          setSessionId(remaining[0]?.session_id || 'default');
        }
        return remaining;
      });
      fetchSessions();
    } catch (_) {}
  }, [sessionId]);

  // ── View metadata (non-chat views only) ───────────────────────────────────

  const VIEW_META = {
    research:    { title: 'Research Workspace',   subtitle: 'Goal · Knowledge · Experiments · Decisions' },
    papers:      { title: 'Papers & TDS Library', subtitle: `${counts.documents} documents indexed` },
    experiments: { title: 'Experiment History',   subtitle: `${counts.experiments} experiments` },
    results:     { title: 'Results & Metrics',    subtitle: 'Comparative analysis across iterations' },
    decisions:   { title: 'Decision Log',         subtitle: 'Review and approve experiment decisions' },
  };
  const meta = VIEW_META[activeNav];

  // ── Loop handlers ──────────────────────────────────────────────────────────

  const handleToggleLoop = useCallback(async ({ active, goal, weights, schema_id }) => {
    if (!active) { await handleStopLoop(); return; }
    setLoopLoading(true);
    loopLoadingRef.current = true;
    try {
      const res = await fetch(`${API_BASE}/api/loop/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal, weights, schema_id: schema_id || null }),
      });
      if (res.ok) setLoopState(await res.json());
    } catch (e) { console.error('Loop start error:', e); }
    finally { setLoopLoading(false); loopLoadingRef.current = false; }
  }, []);

  const handleRunIteration = useCallback(async ({ goal, weights, schema_id }) => {
    setLoopLoading(true);
    loopLoadingRef.current = true;
    const endpoint = (!loopState || loopState.status === 'idle' || loopState.status === 'stopped')
      ? `${API_BASE}/api/loop/start`
      : `${API_BASE}/api/loop/iterate`;
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal, weights, schema_id: schema_id || null }),
      });
      if (res.ok) setLoopState(await res.json());
    } catch (e) { console.error('Iteration error:', e); }
    finally { setLoopLoading(false); loopLoadingRef.current = false; }
  }, [loopState]);

  const handleApprove = useCallback(async () => {
    setLoopLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/loop/approve`, { method: 'POST' });
      if (res.ok) setLoopState(await res.json());
    } catch (e) { console.error('Approve error:', e); }
    finally { setLoopLoading(false); }
  }, []);

  const handleStopLoop = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/loop/stop`, { method: 'POST' });
      if (res.ok) setLoopState(await res.json());
    } catch (e) { console.error('Stop error:', e); }
  }, []);

  const handleEditHypothesis = useCallback(async (hypothesis) => {
    try {
      const res = await fetch(`${API_BASE}/api/loop/hypothesis`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hypothesis }),
      });
      if (res.ok) fetchLoopStatus();
    } catch (e) { console.error('Edit hypothesis error:', e); }
  }, []);

  const handleExport = () => {
    const data = { timestamp: new Date().toISOString(), loopState, counts };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `decision-log-${Date.now()}.json`; a.click();
    URL.revokeObjectURL(url);
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  const isChat = activeNav === 'chat';

  return (
    <div className="app-shell">
      <Sidebar
        active={activeNav}
        onNav={setActiveNav}
        counts={counts}
        collapsed={sidebarCollapsed}
        onToggleCollapse={handleToggleCollapse}
        onOpenSettings={() => setSettingsOpen(true)}
        sessions={sessions}
        activeSessionId={sessionId}
        onSessionChange={handleSessionChange}
        onNewSession={handleNewSession}
        onDeleteSession={handleDeleteSession}
      />
      {settingsOpen && <SettingsPanel onClose={() => setSettingsOpen(false)} />}

      <div className="main-content">
        {/* Topbar — hidden for chat (chat is full-screen like Claude) */}
        {!isChat && (
          <div className="topbar">
            <div>
              <div className="topbar-title">{meta?.title}</div>
              <div className="topbar-subtitle">{meta?.subtitle}</div>
            </div>
            <div className="topbar-actions">
              <IterBadge loopState={loopState} loading={loopLoading} />
              <button className="btn btn-ghost btn-sm" onClick={handleExport}>Export</button>
            </div>
          </div>
        )}

        <div className="workspace" style={{ padding: isChat ? 0 : 'var(--pad-lg)' }}>
          <div key={activeNav} className="view-transition">
            {isChat && (
              <ChatView
                sessionId={sessionId}
                onSessionDeleted={fetchSessions}
              />
            )}
            {activeNav === 'research' && (
              <ResearchView
                loopState={loopState}
                loopLoading={loopLoading}
                onSelectExp={setSelectedExp}
                selectedExp={selectedExp}
                onToggleLoop={handleToggleLoop}
                onRunIteration={handleRunIteration}
                onApprove={handleApprove}
                onEditHypothesis={handleEditHypothesis}
                onStopLoop={handleStopLoop}
              />
            )}
            {activeNav === 'papers'      && <PapersView />}
            {activeNav === 'experiments' && <ExperimentsView />}
            {activeNav === 'results'     && <ResultsOnlyView />}
            {activeNav === 'decisions'   && (
              <DecisionsView
                loopState={loopState}
                loopLoading={loopLoading}
                onApprove={handleApprove}
                onEditHypothesis={handleEditHypothesis}
                onStopLoop={handleStopLoop}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── View layouts ──────────────────────────────────────────────────────────────

function ChatView({ sessionId, onSessionDeleted }) {
  return (
    <div style={{ flex: '1 1 0', minHeight: 0, overflow: 'hidden' }}>
      <ChatPanel sessionId={sessionId} onSessionDeleted={onSessionDeleted} />
    </div>
  );
}

function ResearchView({ loopState, loopLoading, onSelectExp, selectedExp, onToggleLoop, onRunIteration, onApprove, onEditHypothesis, onStopLoop }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--pad-md)', height: '100%', overflow: 'hidden' }}>
      <GoalPanel loopState={loopState} loopLoading={loopLoading} onToggleLoop={onToggleLoop} onRunIteration={onRunIteration} />
      <div style={{ display: 'flex', gap: 'var(--pad-md)', flex: '1 1 0', minHeight: 0, overflow: 'hidden' }}>
        <div style={{ flex: '0 0 320px', overflow: 'hidden' }}><KnowledgePanel /></div>
        <div style={{ flex: '1 1 0', overflow: 'hidden' }}><ExperimentDashboard loopState={loopState} onSelect={onSelectExp} /></div>
      </div>
      <div style={{ display: 'flex', gap: 'var(--pad-md)', flex: '1 1 0', minHeight: 0, overflow: 'hidden' }}>
        <div style={{ flex: '1 1 0', overflow: 'hidden' }}><ResultsPanel selectedExp={selectedExp} loopState={loopState} /></div>
        <div style={{ flex: '1 1 0', overflow: 'hidden' }}>
          <DecisionPanel loopState={loopState} loopLoading={loopLoading} onApprove={onApprove} onEditHypothesis={onEditHypothesis} onStopLoop={onStopLoop} />
        </div>
      </div>
    </div>
  );
}

function ExperimentsView() {
  return <div style={{ height: '100%', overflow: 'hidden' }}><ExperimentsPanel /></div>;
}

function ResultsOnlyView() {
  return <div style={{ height: '100%', overflow: 'hidden' }}><ResultsPanel /></div>;
}

function DecisionsView({ loopState, loopLoading, onApprove, onEditHypothesis, onStopLoop }) {
  return (
    <div style={{ display: 'flex', gap: 'var(--pad-md)', height: '100%', overflow: 'hidden' }}>
      <div style={{ flex: '1 1 0', overflow: 'hidden' }}>
        <DecisionPanel loopState={loopState} loopLoading={loopLoading} onApprove={onApprove} onEditHypothesis={onEditHypothesis} onStopLoop={onStopLoop} />
      </div>
      <div style={{ flex: '0 0 340px', overflow: 'hidden' }}><KnowledgePanel /></div>
    </div>
  );
}

// ── IterBadge ─────────────────────────────────────────────────────────────────

function IterBadge({ loopState, loading }) {
  const iter   = loopState?.iteration ?? 0;
  const status = loopState?.status ?? 'idle';
  const statusColor = {
    running:           'var(--score-high)',
    awaiting_approval: 'var(--accent)',
    stopped:           'var(--text-muted)',
    idle:              'var(--text-muted)',
  }[status] ?? 'var(--text-muted)';

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      background: 'var(--bg-raised)', border: '1px solid var(--glass-border)',
      borderRadius: 'var(--r-md)', padding: '4px 12px',
      fontSize: 10, fontFamily: 'var(--font-mono)', letterSpacing: '0.08em',
    }}>
      {loading && <span style={{ color: 'var(--accent)', animation: 'pulse 1s ease-in-out infinite', fontSize: 12 }}>◦</span>}
      <span style={{ color: 'var(--text-muted)', textTransform: 'uppercase' }}>Loop</span>
      <span style={{ color: statusColor, fontWeight: 500 }}>
        {loading ? 'RUNNING' : iter > 0 ? `ITER ${iter}` : 'IDLE'}
      </span>
      {status === 'awaiting_approval' && !loading && (
        <span style={{ fontSize: 9, color: 'var(--accent)' }}>▲ AWAIT</span>
      )}
    </div>
  );
}
