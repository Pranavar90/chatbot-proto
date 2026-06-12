import { useState, useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  MessageSquare, Send, Trash2, FileText, Loader,
  Settings, Plus, X, ShieldCheck, Globe, Atom,
  BookOpen, ClipboardCheck, ScanSearch, ChevronDown,
} from 'lucide-react';

const API_BASE = 'http://localhost:8000';

const EASE_OUT = [0.22, 1, 0.36, 1];

const AGENTS = [
  { id: 'material-expert',       label: 'Material Expert',    short: 'Expert',     icon: Atom,           desc: 'Technical analysis & comparisons' },
  { id: 'technical-reviewer',    label: 'Tech Reviewer',      short: 'Reviewer',   icon: ClipboardCheck, desc: 'QA & standards compliance' },
  { id: 'literature-researcher', label: 'Lit Researcher',     short: 'Literature', icon: BookOpen,       desc: 'Academic synthesis & review' },
  { id: 'document-parser',       label: 'Doc Parser',         short: 'Parser',     icon: ScanSearch,     desc: 'Extraction quality auditing' },
  { id: 'compliance-auditor',    label: 'Compliance',         short: 'Compliance', icon: ShieldCheck,    desc: 'Standards audit & deviation flags' },
];

function getGreeting(sessionCount) {
  const hour = new Date().getHours();
  const name = 'Pranav';

  const timeGreeting = hour < 5 ? 'Working late'
    : hour < 12 ? 'Good morning'
    : hour < 17 ? 'Good afternoon'
    : hour < 21 ? 'Good evening'
    : 'Good night';

  const subtitle = sessionCount > 0
    ? `${sessionCount} research session${sessionCount > 1 ? 's' : ''} in your workspace`
    : 'Ready to begin your research.';

  return { greeting: `${timeGreeting}, ${name}.`, subtitle };
}

export default function ChatPanel({ sessionId = 'default', onSessionDeleted }) {
  const [messages, setMessages]             = useState([]);
  const [input, setInput]                   = useState('');
  const [loading, setLoading]               = useState(false);
  const [role, setRole]                     = useState('material-expert');
  const [complianceStandard, setComplianceStandard] = useState('');
  const [showComplianceManager, setShowComplianceManager] = useState(false);
  const [complianceStandards, setComplianceStandards]     = useState([]);
  const [forceWebSearch, setForceWebSearch] = useState(true);
  const [agentOpen, setAgentOpen]           = useState(false);
  const [sessionCount, setSessionCount]     = useState(0);

  const messagesEndRef = useRef(null);
  const inputRef       = useRef(null);
  const controllerRef  = useRef(null);
  const agentDropRef   = useRef(null);

  const activeAgent = AGENTS.find(a => a.id === role) || AGENTS[0];

  /* ── Fetch session count for greeting ────────────────────── */
  useEffect(() => {
    fetch(`${API_BASE}/api/chat/sessions`)
      .then(r => r.json())
      .then(d => setSessionCount((d.sessions || []).length))
      .catch(() => {});
  }, []);

  /* ── Session switch: abort in-flight, reset state ─────────── */
  useEffect(() => {
    if (controllerRef.current) {
      controllerRef.current.abort();
      controllerRef.current = null;
    }
    setLoading(false);
    setMessages([]);
    fetchHistory();
    fetchComplianceStandards();
  }, [sessionId]);

  /* ── Auto-scroll ───────────────────────────────────────────── */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  /* ── Close agent dropdown on outside click ─────────────────── */
  useEffect(() => {
    if (!agentOpen) return;
    const handler = (e) => {
      if (agentDropRef.current && !agentDropRef.current.contains(e.target)) {
        setAgentOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [agentOpen]);

  const fetchComplianceStandards = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/compliance`);
      if (res.ok) {
        const data = await res.json();
        setComplianceStandards(data.standards || []);
      }
    } catch (_) {}
  };

  const fetchHistory = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/chat/sessions/${sessionId}/history?limit=20`);
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages || []);
      }
    } catch (err) {
      console.error('Failed to fetch history:', err);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const userMessage = input.trim();
    setInput('');
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }
    setLoading(true);

    setMessages(prev => [...prev, {
      role: 'user',
      content: userMessage,
      timestamp: new Date().toISOString(),
    }]);

    const controller = new AbortController();
    controllerRef.current = controller;
    const timeoutId = setTimeout(() => controller.abort(), 120_000);

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        signal: controller.signal,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMessage,
          role,
          session_id: sessionId,
          include_context: true,
          compliance_standard: role === 'compliance-auditor' ? complianceStandard : '',
          force_web_search: forceWebSearch,
        }),
      });
      clearTimeout(timeoutId);

      if (res.ok) {
        const data = await res.json();
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: data.response,
          sources: data.sources,
          web_used: data.web_used,
          timestamp: new Date().toISOString(),
        }]);
        onSessionDeleted?.();
      } else {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: 'Error: Failed to get response from the server.',
          timestamp: new Date().toISOString(),
        }]);
      }
    } catch (err) {
      clearTimeout(timeoutId);
      const msg = err.name === 'AbortError'
        ? 'Request timed out — the model is taking too long. Try a shorter prompt or check system status.'
        : `Connection error: ${err.message}`;
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: msg,
        timestamp: new Date().toISOString(),
      }]);
    }

    controllerRef.current = null;
    setLoading(false);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const handleClearSession = async () => {
    if (!confirm('Clear this session? This cannot be undone.')) return;
    try {
      await fetch(`${API_BASE}/api/chat/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
      setMessages([]);
      onSessionDeleted?.();
    } catch (err) {
      console.error('Failed to clear session:', err);
    }
  };

  const sessionLabel = sessionId === 'default'
    ? 'Materials Chat'
    : sessionId.replace('session-', 'Session ');

  const greeting = useMemo(() => getGreeting(sessionCount), [sessionCount]);

  return (
    <>
      <div className="glass-panel" style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        width: '100%',
      }}>

        {/* ── Header ─────────────────────────────────────────── */}
        <div className="panel-header" style={{ justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <MessageSquare size={12} style={{ color: 'var(--accent)', opacity: 0.65 }} />
            <span className="panel-title">{sessionLabel}</span>
            {messages.length > 0 && (
              <span style={{
                fontSize: 9,
                fontFamily: 'var(--font-mono)',
                color: 'var(--text-muted)',
                letterSpacing: '0.06em',
              }}>
                {messages.length} msg
              </span>
            )}
          </div>
          <button
            className="btn btn-ghost"
            onClick={handleClearSession}
            title="Clear session"
            style={{ padding: '3px 7px' }}
          >
            <Trash2 size={11} />
          </button>
        </div>

        {/* ── Agent bar — expert module cards ────────────────── */}
        <AgentBar
          agents={AGENTS}
          activeAgent={activeAgent}
          role={role}
          setRole={setRole}
          agentOpen={agentOpen}
          setAgentOpen={setAgentOpen}
          agentDropRef={agentDropRef}
          complianceStandard={complianceStandard}
          setComplianceStandard={setComplianceStandard}
          complianceStandards={complianceStandards}
          onOpenManager={() => setShowComplianceManager(true)}
        />

        {/* ── Messages ───────────────────────────────────────── */}
        <div style={{
          flex: 1,
          overflowY: 'auto',
          overflowX: 'hidden',
          padding: '28px 32px 20px',
          minHeight: 0,
        }}>
          <AnimatePresence mode="popLayout">
            {messages.length === 0 ? (
              <EmptyState
                key="empty"
                role={role}
                greeting={greeting}
                onSuggest={(text) => { setInput(text); inputRef.current?.focus(); }}
              />
            ) : (
              messages.map((msg, i) => (
                <Message key={`${i}-${msg.timestamp}`} msg={msg} index={i} />
              ))
            )}
          </AnimatePresence>

          {loading && <ThinkingIndicator />}
          <div ref={messagesEndRef} />
        </div>

        {/* ── Composer ───────────────────────────────────────── */}
        <div className="composer">
          <div className="composer-inner">
            {/* Toolbar row */}
            <div className="composer-toolbar">
              {/* Left controls */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                {/* Agent indicator */}
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  fontSize: 9, fontFamily: 'var(--font-mono)',
                  color: 'var(--text-muted)', letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                }}>
                  <activeAgent.icon size={10} style={{ color: 'var(--accent)', opacity: 0.7 }} />
                  {activeAgent.short}
                </div>

                {/* Divider */}
                <div style={{ width: 1, height: 12, background: 'rgba(255,255,255,0.08)' }} />

                {/* Web search toggle */}
                <button
                  title={forceWebSearch ? 'Web search ON — click to disable' : 'Web search OFF — AI decides'}
                  onClick={() => setForceWebSearch(v => !v)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 4,
                    padding: '3px 8px',
                    background: forceWebSearch ? 'var(--cyan-dim)' : 'transparent',
                    border: `1px solid ${forceWebSearch ? 'var(--cyan-border)' : 'rgba(255,255,255,0.07)'}`,
                    borderRadius: 'var(--r-sm)',
                    cursor: 'pointer',
                    color: forceWebSearch ? 'var(--cyan)' : 'var(--text-muted)',
                    fontSize: '9px',
                    fontFamily: 'var(--font-mono)',
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    transition: 'all 0.15s',
                    whiteSpace: 'nowrap',
                  }}
                >
                  <Globe size={10} />
                  WEB
                </button>
              </div>

              {/* Send button */}
              <motion.button
                onClick={handleSend}
                disabled={loading || !input.trim()}
                whileHover={(!loading && input.trim()) ? { scale: 1.02 } : {}}
                whileTap={(!loading && input.trim()) ? { scale: 0.97 } : {}}
                transition={{ type: 'spring', stiffness: 400, damping: 25 }}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  gap: 6,
                  padding: '7px 16px',
                  background: loading || !input.trim() ? 'transparent' : 'var(--accent)',
                  border: `1px solid ${loading || !input.trim() ? 'rgba(255,255,255,0.08)' : 'var(--accent-bright)'}`,
                  borderRadius: 'var(--r-sm)',
                  cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
                  color: loading || !input.trim() ? 'var(--text-muted)' : '#f0ede8',
                  fontSize: 11,
                  fontFamily: 'var(--font-mono)',
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  opacity: loading ? 0.5 : 1,
                  transition: 'background 0.15s, border-color 0.15s, color 0.15s, opacity 0.15s',
                }}
              >
                {loading
                  ? <Loader size={12} style={{ animation: 'spin 1s linear infinite' }} />
                  : <Send size={12} />
                }
                <span>{loading ? 'Thinking' : 'Send'}</span>
              </motion.button>
            </div>

            {/* Textarea */}
            <textarea
              ref={inputRef}
              className="composer-textarea"
              placeholder="Ask anything about materials, composites, or your indexed documents..."
              value={input}
              rows={1}
              onChange={e => {
                setInput(e.target.value);
                e.target.style.height = 'auto';
                e.target.style.height = Math.min(e.target.scrollHeight, 180) + 'px';
              }}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              disabled={loading}
            />
          </div>

          <div className="composer-hint">
            Enter to send &middot; Shift+Enter for new line &middot; Web {forceWebSearch ? 'ON' : 'OFF'}
          </div>
        </div>
      </div>

      {showComplianceManager && (
        <ComplianceManagerModal
          standards={complianceStandards}
          onClose={() => { setShowComplianceManager(false); fetchComplianceStandards(); }}
        />
      )}
    </>
  );
}

/* ── Agent bar — expert module cards ──────────────────────────── */
function AgentBar({ agents, activeAgent, role, setRole, agentOpen, setAgentOpen, agentDropRef,
  complianceStandard, setComplianceStandard, complianceStandards, onOpenManager }) {

  return (
    <div className="agent-bar">
      <span style={{
        fontSize: 9, fontFamily: 'var(--font-mono)',
        color: 'var(--text-muted)', letterSpacing: '0.12em',
        textTransform: 'uppercase', flexShrink: 0,
        fontWeight: 500,
      }}>
        Agents
      </span>

      {/* Agent cards */}
      <div style={{ display: 'flex', gap: 6, flex: 1, overflowX: 'auto' }}>
        {agents.map(agent => {
          const isActive = role === agent.id;
          const AgentIcon = agent.icon;
          return (
            <motion.button
              key={agent.id}
              className={`agent-card${isActive ? ' active' : ''}`}
              onClick={() => setRole(agent.id)}
              title={agent.desc}
              whileHover={{ scale: 1.02, y: -1 }}
              whileTap={{ scale: 0.97 }}
              transition={{ type: 'spring', stiffness: 400, damping: 25 }}
            >
              {isActive && <div className="agent-card-online" />}
              <div className="agent-card-header">
                <AgentIcon size={14} className="agent-card-icon" />
                <span className="agent-card-name">{agent.short}</span>
              </div>
              <span className="agent-card-desc">{agent.desc}</span>
            </motion.button>
          );
        })}
      </div>

      {/* Compliance standard selector (only for compliance-auditor) */}
      {role === 'compliance-auditor' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
          <ShieldCheck size={10} style={{ color: 'var(--accent)', opacity: 0.7 }} />
          <select
            value={complianceStandard}
            onChange={e => setComplianceStandard(e.target.value)}
            style={{
              background: 'var(--bg-raised)',
              border: '1px solid var(--border-glass)',
              borderRadius: 'var(--r-sm)',
              color: 'var(--text-secondary)',
              fontSize: 10,
              padding: '3px 8px',
              cursor: 'pointer',
              fontFamily: 'var(--font-mono)',
              outline: 'none',
            }}
          >
            <option value="" style={{ background: 'var(--bg-base)' }}>Auto-detect standard</option>
            {complianceStandards.filter(s => s.key).map(s => (
              <option key={s.key} value={s.key} style={{ background: 'var(--bg-base)' }}>
                {s.display}{s.is_builtin ? '' : ' *'}
              </option>
            ))}
          </select>
          <button
            className="btn btn-ghost"
            onClick={onOpenManager}
            title="Manage compliance standards"
            style={{ padding: '3px 6px' }}
          >
            <Settings size={10} />
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Individual message ────────────────────────────────────────── */
function Message({ msg, index }) {
  const delay = Math.min(index * 0.02, 0.12);

  if (msg.role === 'user') {
    return (
      <motion.div
        className="msg-user"
        initial={{ opacity: 0, y: 6, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.35, ease: EASE_OUT, delay }}
      >
        <div>
          <div className="msg-user-label">You</div>
          <div className="msg-user-bubble">{msg.content}</div>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      className="msg-ai"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: EASE_OUT, delay }}
    >
      {/* Avatar */}
      <div className="msg-ai-avatar">P</div>

      {/* Content */}
      <div className="msg-ai-body">
        <div className="msg-ai-label">
          <span>Porter AI</span>
          {msg.web_used && (
            <span className="web-badge">
              <Globe size={8} /> WEB
            </span>
          )}
        </div>
        <motion.div
          className="msg-ai-content"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.4, delay: delay + 0.1 }}
        >
          {msg.content}
        </motion.div>
        {msg.sources && msg.sources.length > 0 && (
          <SourcePills sources={msg.sources} />
        )}
      </div>
    </motion.div>
  );
}

/* ── Thinking indicator ────────────────────────────────────────── */
function ThinkingIndicator() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setElapsed(s => s + 1), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <motion.div
      className="thinking-indicator"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3, ease: EASE_OUT }}
    >
      <div className="msg-ai-avatar" style={{ opacity: 0.4, animation: 'breathe 2s ease-in-out infinite' }}>P</div>
      <div className="thinking-content">
        <div className="thinking-label">
          <span>Analyzing</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--accent-bright)' }}>
            {elapsed}s
          </span>
          {elapsed >= 15 && (
            <span style={{ fontSize: 9, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              Local model — please wait
            </span>
          )}
        </div>
        <div className="thinking-bar-track">
          <div className="thinking-bar-fill" />
        </div>
      </div>
    </motion.div>
  );
}

/* ── Empty state / Greeting ───────────────────────────────────── */
function EmptyState({ role, greeting, onSuggest }) {
  const isCompliance = role === 'compliance-auditor';
  const suggestions = isCompliance
    ? [
        'Audit this TDS against ISO 14125 flexural standards',
        'Check composite layup schedule for IEC EMI compliance',
        'Review nanocomposite loading for reporting standards',
      ]
    : [
        'Compare tensile modulus of carbon fiber epoxy composites',
        'What are the optimal cure cycles for bismaleimide resins?',
        'Summarize fracture toughness data from indexed papers',
      ];

  return (
    <motion.div
      className="empty-state"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5, ease: EASE_OUT }}
    >
      <motion.div
        className="greeting-heading"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: EASE_OUT, delay: 0.05 }}
      >
        {greeting.greeting}
      </motion.div>
      <motion.div
        className="greeting-subtitle"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: EASE_OUT, delay: 0.12 }}
      >
        {greeting.subtitle}
      </motion.div>

      <div className="empty-state-suggestions">
        {suggestions.map((text, i) => (
          <motion.button
            key={i}
            className="suggestion-chip"
            onClick={() => onSuggest(text)}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: EASE_OUT, delay: 0.2 + i * 0.08 }}
            whileHover={{ scale: 1.01, y: -1 }}
            whileTap={{ scale: 0.99 }}
          >
            <span style={{
              fontSize: 10, fontFamily: 'var(--font-mono)',
              color: 'var(--accent)', opacity: 0.8,
              letterSpacing: '0.06em', flexShrink: 0,
              fontWeight: 500,
            }}>
              {String(i + 1).padStart(2, '0')}
            </span>
            <span>{text}</span>
          </motion.button>
        ))}
      </div>
    </motion.div>
  );
}

/* ── Source pills ──────────────────────────────────────────────── */
function SourcePills({ sources }) {
  const [expandedIdx, setExpandedIdx] = useState(null);

  const scoreColor = (s) => {
    if (s >= 0.8) return 'var(--score-high)';
    if (s >= 0.5) return 'var(--score-mid)';
    return 'var(--score-low)';
  };

  return (
    <div className="sources-section">
      <div className="sources-label">Sources ({sources.length})</div>
      <div className="sources-grid">
        {sources.map((s, i) => {
          const isOpen = expandedIdx === i;
          return (
            <div key={i}>
              <button
                className={`source-pill${isOpen ? ' active' : ''}`}
                onClick={() => setExpandedIdx(isOpen ? null : i)}
              >
                <FileText size={9} style={{ flexShrink: 0 }} />
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.filename}
                </span>
                {s.score != null && (
                  <span className="source-pill-score" style={{ color: scoreColor(s.score) }}>
                    {(s.score * 100).toFixed(0)}%
                  </span>
                )}
              </button>
              <AnimatePresence>
                {isOpen && s.preview && (
                  <motion.div
                    className="source-expand"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2, ease: EASE_OUT }}
                  >
                    {s.preview}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Compliance manager modal ──────────────────────────────────── */
function ComplianceManagerModal({ standards, onClose }) {
  const [tab, setTab]         = useState('list');
  const [form, setForm]       = useState({ key: '', display: '', system_prompt: '', constraint_summary: '' });
  const [saving, setSaving]   = useState(false);
  const [error, setError]     = useState('');
  const [deleting, setDeleting] = useState(null);

  const handleSave = async () => {
    if (!form.key.trim() || !form.display.trim() || !form.system_prompt.trim()) {
      setError('Key, display name, and system prompt are required.');
      return;
    }
    setSaving(true); setError('');
    try {
      const res = await fetch(`${API_BASE}/api/compliance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (res.ok) {
        setForm({ key: '', display: '', system_prompt: '', constraint_summary: '' });
        setTab('list'); onClose();
      } else {
        const data = await res.json();
        setError(data.detail || 'Save failed');
      }
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  const handleDelete = async (key) => {
    if (!confirm(`Delete "${key}"?`)) return;
    setDeleting(key);
    try {
      await fetch(`${API_BASE}/api/compliance/${encodeURIComponent(key)}`, { method: 'DELETE' });
      onClose();
    } catch (_) {}
    setDeleting(null);
  };

  const inputStyle = {
    width: '100%',
    background: 'var(--bg-raised)',
    border: '1px solid var(--border-glass)',
    borderRadius: 'var(--r-sm)',
    color: 'var(--text-primary)',
    fontSize: 12,
    padding: '8px 11px',
    outline: 'none',
    boxSizing: 'border-box',
    fontFamily: 'var(--font-body)',
    transition: 'border-color 0.15s',
  };

  return (
    <div
      className="glass-overlay"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        className="glass-panel-elevated"
        style={{ width: 560, maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}
        initial={{ opacity: 0, scale: 0.96, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.3, ease: EASE_OUT }}
      >
        {/* Modal header */}
        <div className="panel-header" style={{ flexShrink: 0 }}>
          <ShieldCheck size={12} style={{ color: 'var(--accent)' }} />
          <span className="panel-title">Compliance Standards</span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 5 }}>
            <button
              className={`btn btn-sm ${tab === 'list' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setTab('list')}
            >
              Standards
            </button>
            <button
              className={`btn btn-sm ${tab === 'add' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => { setTab('add'); setError(''); }}
            >
              <Plus size={9} /> Add
            </button>
            <button className="btn btn-ghost btn-sm" onClick={onClose}>
              <X size={12} />
            </button>
          </div>
        </div>

        {/* Modal body */}
        <div style={{ flex: 1, overflow: 'auto', padding: '14px 16px' }}>
          {tab === 'list' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {standards.filter(s => s.key).map(s => (
                <div key={s.key} style={{
                  display: 'flex', alignItems: 'flex-start', gap: 10,
                  padding: '10px 12px',
                  background: 'var(--bg-raised)',
                  border: '1px solid var(--border-glass)',
                  borderRadius: 'var(--r-md)',
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)' }}>{s.display}</span>
                      {s.is_builtin
                        ? <span className="tag tag-pending">BUILT-IN</span>
                        : <span className="tag tag-warning">CUSTOM</span>
                      }
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2, fontFamily: 'var(--font-mono)' }}>{s.key}</div>
                    {s.constraint_summary && (
                      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4, lineHeight: 1.5 }}>{s.constraint_summary}</div>
                    )}
                  </div>
                  {!s.is_builtin && (
                    <button
                      className="btn btn-sm btn-danger"
                      onClick={() => handleDelete(s.key)}
                      disabled={deleting === s.key}
                    >
                      {deleting === s.key
                        ? <Loader size={11} style={{ animation: 'spin 1s linear infinite' }} />
                        : <Trash2 size={11} />
                      }
                    </button>
                  )}
                </div>
              ))}
              {standards.filter(s => s.key).length === 0 && (
                <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
                  No standards defined yet.
                </div>
              )}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {error && (
                <div style={{
                  padding: '8px 12px',
                  background: 'rgba(136, 32, 32, 0.12)',
                  border: '1px solid rgba(136, 32, 32, 0.28)',
                  borderRadius: 'var(--r-sm)',
                  fontSize: 12, color: 'var(--error)',
                }}>
                  {error}
                </div>
              )}
              <div>
                <div style={{ fontSize: 9, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', marginBottom: 5, letterSpacing: '0.10em', textTransform: 'uppercase' }}>
                  Key <span style={{ color: 'var(--score-low)' }}>*</span>
                </div>
                <input
                  style={inputStyle}
                  placeholder="e.g. ISO-14125-Composites"
                  value={form.key}
                  onChange={e => setForm(f => ({ ...f, key: e.target.value }))}
                  onFocus={e => e.target.style.borderColor = 'var(--border-accent)'}
                  onBlur={e => e.target.style.borderColor = 'var(--border-glass)'}
                />
              </div>
              <div>
                <div style={{ fontSize: 9, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', marginBottom: 5, letterSpacing: '0.10em', textTransform: 'uppercase' }}>
                  Display Name <span style={{ color: 'var(--score-low)' }}>*</span>
                </div>
                <input
                  style={inputStyle}
                  placeholder="e.g. ISO Composite Flexural Testing"
                  value={form.display}
                  onChange={e => setForm(f => ({ ...f, display: e.target.value }))}
                  onFocus={e => e.target.style.borderColor = 'var(--border-accent)'}
                  onBlur={e => e.target.style.borderColor = 'var(--border-glass)'}
                />
              </div>
              <div>
                <div style={{ fontSize: 9, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', marginBottom: 5, letterSpacing: '0.10em', textTransform: 'uppercase' }}>
                  Constraint Summary
                </div>
                <input
                  style={inputStyle}
                  placeholder="e.g. ISO 14125, ISO 14130: Composite mechanical testing"
                  value={form.constraint_summary}
                  onChange={e => setForm(f => ({ ...f, constraint_summary: e.target.value }))}
                  onFocus={e => e.target.style.borderColor = 'var(--border-accent)'}
                  onBlur={e => e.target.style.borderColor = 'var(--border-glass)'}
                />
              </div>
              <div>
                <div style={{ fontSize: 9, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', marginBottom: 5, letterSpacing: '0.10em', textTransform: 'uppercase' }}>
                  System Prompt <span style={{ color: 'var(--score-low)' }}>*</span>
                </div>
                <textarea
                  style={{
                    ...inputStyle,
                    minHeight: 180,
                    resize: 'vertical',
                    fontFamily: 'var(--font-mono)',
                    lineHeight: 1.55,
                    fontSize: 11,
                  }}
                  placeholder={`You are a compliance auditor for [standard].\n\nAUDITOR MANDATE:\n- Check that...\n\nFLAGS:\n- Missing X → NON-CONFORMANCE`}
                  value={form.system_prompt}
                  onChange={e => setForm(f => ({ ...f, system_prompt: e.target.value }))}
                  onFocus={e => e.target.style.borderColor = 'var(--border-accent)'}
                  onBlur={e => e.target.style.borderColor = 'var(--border-glass)'}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                <button className="btn btn-secondary btn-sm" onClick={() => setTab('list')}>Cancel</button>
                <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
                  {saving
                    ? <Loader size={12} style={{ animation: 'spin 1s linear infinite' }} />
                    : <Plus size={12} />
                  }
                  Save Standard
                </button>
              </div>
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
}
