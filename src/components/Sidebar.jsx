import { useRef, useCallback, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import logo from '../../logo.jpg';
import {
  Microscope, FileText, FlaskConical, BarChart3, Brain,
  Cpu, Database, Zap, ChevronLeft, ChevronRight, Settings,
  Plus, Trash2, MessageSquare,
} from 'lucide-react';

const WORKSPACE_ITEMS = [
  { id: 'research',    label: 'Research',    icon: Microscope },
  { id: 'papers',      label: 'Papers',      icon: FileText },
  { id: 'experiments', label: 'Experiments', icon: FlaskConical },
  { id: 'results',     label: 'Results',     icon: BarChart3 },
  { id: 'decisions',   label: 'Decisions',   icon: Brain },
];

const EASE_OUT = [0.22, 1, 0.36, 1];

function relativeTime(iso) {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return 'now';
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

export default function Sidebar({
  active, onNav, counts = {}, collapsed = false,
  onToggleCollapse, onOpenSettings,
  sessions = [], activeSessionId, onSessionChange, onNewSession, onDeleteSession,
}) {
  const navRefs = useRef({});
  const [hoveredSession, setHoveredSession] = useState(null);
  const isChat = active === 'chat';

  const handleKeyDown = useCallback((e, id, index, items) => {
    let nextIndex = index;
    if (e.key === 'ArrowDown') { e.preventDefault(); nextIndex = (index + 1) % items.length; }
    else if (e.key === 'ArrowUp') { e.preventDefault(); nextIndex = (index - 1 + items.length) % items.length; }
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onNav(id); return; }
    if (nextIndex !== index) navRefs.current[items[nextIndex].id]?.focus();
  }, [onNav]);

  const getBadge = (id) => {
    if (id === 'papers')      return counts.documents   || null;
    if (id === 'experiments') return counts.experiments || null;
    return null;
  };

  return (
    <motion.aside
      className={`sidebar${collapsed ? ' collapsed' : ''}`}
      animate={{ width: collapsed ? 56 : 264 }}
      transition={{ duration: 0.28, ease: EASE_OUT }}
    >
      {/* ── Collapse toggle ─────────────────────────────────── */}
      <button
        className="sidebar-collapse-btn"
        onClick={onToggleCollapse}
        title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? <ChevronRight size={11} /> : <ChevronLeft size={11} />}
      </button>

      {/* ── Logo ───────────────────────────────────────────── */}
      <div className="sidebar-logo">
        <div className="logo-mark">
          {collapsed ? (
            <div className="logo-icon">M</div>
          ) : (
            <img
              src={logo}
              alt="Planet Material Labs"
              style={{ height: 32, width: 'auto', objectFit: 'contain', display: 'block' }}
            />
          )}
        </div>
      </div>

      {/* ── New Session ────────────────────────────────────── */}
      <div style={{ padding: collapsed ? '10px 8px 6px' : '10px 10px 6px', flexShrink: 0 }}>
        <motion.button
          onClick={onNewSession}
          title="New session"
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.98 }}
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: collapsed ? 'center' : 'flex-start',
            gap: 8,
            padding: collapsed ? '9px' : '8px 12px',
            background: 'transparent',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: '8px',
            cursor: 'pointer',
            color: 'var(--text-secondary)',
            fontSize: 12,
            fontFamily: 'var(--font-body)',
            transition: 'all 0.18s cubic-bezier(0.22, 1, 0.36, 1)',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.borderColor = 'rgba(196,112,42,0.28)';
            e.currentTarget.style.color = 'var(--text-primary)';
            e.currentTarget.style.background = 'rgba(196,112,42,0.05)';
            e.currentTarget.style.boxShadow = '0 0 0 3px rgba(196,112,42,0.06)';
          }}
          onMouseLeave={e => {
            e.currentTarget.style.borderColor = 'rgba(255,255,255,0.07)';
            e.currentTarget.style.color = 'var(--text-secondary)';
            e.currentTarget.style.background = 'transparent';
            e.currentTarget.style.boxShadow = 'none';
          }}
        >
          <Plus size={13} style={{ flexShrink: 0, color: 'var(--accent)', opacity: 0.8 }} />
          {!collapsed && (
            <span className="sidebar-label-text" style={{ fontSize: 12 }}>New Session</span>
          )}
        </motion.button>
      </div>

      {/* ── Session list ────────────────────────────────────── */}
      {!collapsed ? (
        <div style={{
          flex: 1,
          overflowY: 'auto',
          overflowX: 'hidden',
          padding: '0 6px',
          minHeight: 0,
        }}>
          <AnimatePresence mode="popLayout">
            {sessions.length === 0 ? (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                style={{
                  padding: '20px 12px',
                  fontSize: 10,
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--text-muted)',
                  letterSpacing: '0.06em',
                  textAlign: 'center',
                  lineHeight: 1.6,
                }}
              >
                No conversations yet.{'\n'}Start one above.
              </motion.div>
            ) : (
              sessions.map(s => (
                <SessionEntry
                  key={s.session_id}
                  session={s}
                  active={s.session_id === activeSessionId && isChat}
                  hovered={hoveredSession === s.session_id}
                  onHover={setHoveredSession}
                  onClick={() => onSessionChange(s.session_id)}
                  onDelete={(e) => onDeleteSession(s.session_id, e)}
                />
              ))
            )}
          </AnimatePresence>
        </div>
      ) : (
        /* Collapsed: single chat icon */
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 4 }}>
          <button
            onClick={onNewSession}
            title="New chat"
            style={{
              width: 34, height: 34,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: isChat ? 'rgba(196,112,42,0.10)' : 'transparent',
              border: isChat ? '1px solid rgba(196,112,42,0.28)' : '1px solid transparent',
              borderRadius: '6px', cursor: 'pointer',
              color: isChat ? 'var(--accent)' : 'var(--text-muted)',
              transition: 'all 0.15s',
            }}
          >
            <MessageSquare size={14} />
          </button>
        </div>
      )}

      {/* ── Divider + Workspace section ─────────────────────── */}
      <div style={{ flexShrink: 0 }}>
        <div style={{
          height: 1,
          background: 'rgba(255,255,255,0.05)',
          margin: '4px 0 0',
        }} />

        {!collapsed && (
          <p className="sidebar-section-label" style={{ paddingTop: 8 }}>Workspace</p>
        )}

        <ul
          className="sidebar-nav stagger-children"
          role="menubar"
          aria-label="Workspace navigation"
          style={{ flex: 'none', paddingBottom: 4 }}
        >
          {WORKSPACE_ITEMS.map(({ id, label, icon: Icon }, index) => {
            const badge = getBadge(id);
            const isActive = active === id;
            return (
              <motion.li
                key={id}
                id={`nav-${id}`}
                className={`sidebar-nav-item${isActive ? ' active' : ''}`}
                onClick={() => onNav(id)}
                onKeyDown={(e) => handleKeyDown(e, id, index, WORKSPACE_ITEMS)}
                ref={(el) => navRefs.current[id] = el}
                role="menuitem"
                tabIndex={isActive ? 0 : -1}
                aria-current={isActive ? 'page' : undefined}
                title={collapsed ? label : undefined}
                whileHover={{ x: 2 }}
                transition={{ duration: 0.14, ease: EASE_OUT }}
              >
                <span className="nav-icon"><Icon size={14} /></span>
                <span className="sidebar-label-text">{label}</span>
                {badge > 0 && !collapsed && (
                  <span className="nav-badge">{badge > 99 ? '99+' : badge}</span>
                )}
              </motion.li>
            );
          })}
        </ul>
      </div>

      {/* ── System status + Settings ─────────────────────────── */}
      <div className="sidebar-status">
        {!collapsed && (
          <p className="sidebar-section-label" style={{ padding: '0 0 6px', fontSize: 9 }}>System</p>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <StatusRow
            icon={<Cpu size={10} />}
            label="Ollama"
            state="online"
            detail="qwen2.5:3b"
            collapsed={collapsed}
          />
          <StatusRow
            icon={<Database size={10} />}
            label="Qdrant"
            state="online"
            detail={`${counts.qdrant_parsed || 0} pts`}
            collapsed={collapsed}
          />
          <StatusRow
            icon={<Zap size={10} />}
            label="Engine"
            state="online"
            detail={`${counts.experiments || 0} exps`}
            collapsed={collapsed}
          />
        </div>

        <button
          onClick={onOpenSettings}
          title="Settings"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: collapsed ? 'center' : 'flex-start',
            gap: 7,
            width: '100%',
            marginTop: 8,
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--text-muted)',
            padding: collapsed ? '6px 0' : '5px 2px',
            borderRadius: 'var(--r-sm)',
            transition: 'color 0.15s',
            fontFamily: 'var(--font-body)',
            fontSize: 12,
          }}
          onMouseEnter={e => e.currentTarget.style.color = 'var(--text-secondary)'}
          onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}
        >
          <Settings size={12} style={{ flexShrink: 0 }} />
          {!collapsed && <span className="sidebar-label-text">Settings</span>}
        </button>
      </div>
    </motion.aside>
  );
}

/* ── Session entry ─────────────────────────────────────────────── */
function SessionEntry({ session, active, hovered, onHover, onClick, onDelete }) {
  const label = session.first_message
    ? session.first_message.slice(0, 34) + (session.first_message.length > 34 ? '...' : '')
    : session.session_id === 'default'
      ? 'Default session'
      : session.session_id.replace('session-', 'Session #');

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -8 }}
      transition={{ duration: 0.2, ease: EASE_OUT }}
      onClick={onClick}
      onMouseEnter={() => onHover(session.session_id)}
      onMouseLeave={() => onHover(null)}
      style={{
        position: 'relative',
        padding: '8px 10px 8px 14px',
        marginBottom: 1,
        cursor: 'pointer',
        background: active
          ? 'rgba(196,112,42,0.06)'
          : hovered
            ? 'rgba(255,255,255,0.025)'
            : 'transparent',
        transition: 'background 0.14s',
        borderRadius: '5px',
      }}
    >
      {/* Active left accent bar */}
      {active && (
        <motion.div
          layoutId="session-accent"
          style={{
            position: 'absolute', left: 0, top: '50%',
            transform: 'translateY(-50%)',
            width: 2,
            height: '55%',
            background: 'var(--accent)',
            borderRadius: '0 1px 1px 0',
          }}
          transition={{ type: 'spring', stiffness: 400, damping: 28 }}
        />
      )}

      {/* Title */}
      <div style={{
        fontSize: 12,
        color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
        lineHeight: 1.4,
        paddingRight: hovered ? 22 : 0,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
        transition: 'padding-right 0.12s, color 0.12s',
        fontFamily: 'var(--font-body)',
        fontWeight: active ? 450 : 400,
      }}>
        {label}
      </div>

      {/* Meta row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 2 }}>
        {session.message_count > 0 && (
          <span style={{
            fontSize: 10, fontFamily: 'var(--font-mono)',
            color: 'var(--text-muted)',
          }}>
            {session.message_count} msg
          </span>
        )}
        {session.last_active && (
          <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
            {relativeTime(session.last_active)}
          </span>
        )}
      </div>

      {/* Delete button — appears on hover with motion */}
      <AnimatePresence>
        {hovered && (
          <motion.button
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            transition={{ duration: 0.12 }}
            onClick={onDelete}
            title="Delete session"
            style={{
              position: 'absolute', right: 6, top: '50%',
              transform: 'translateY(-50%)',
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--text-muted)', padding: 3, borderRadius: 3,
              display: 'flex', alignItems: 'center',
              transition: 'color 0.12s',
            }}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--error)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}
          >
            <Trash2 size={11} />
          </motion.button>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

/* ── Status row ────────────────────────────────────────────────── */
function StatusRow({ icon, label, state, detail, collapsed }) {
  return (
    <div
      className="status-dot"
      style={{ justifyContent: collapsed ? 'center' : 'space-between' }}
      title={collapsed ? `${label}: ${detail}` : undefined}
    >
      <div style={{
        display: 'flex', alignItems: 'center', gap: 5,
        color: 'var(--text-muted)', fontSize: 10,
      }}>
        <span className={`status-dot-indicator${state !== 'online' ? ' offline' : ''}`} />
        <span style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center' }}>{icon}</span>
        {!collapsed && <span className="status-label sidebar-label-text" style={{ fontSize: 10, color: 'var(--text-muted)' }}>{label}</span>}
      </div>
      {!collapsed && (
        <span className="status-detail sidebar-label-text" style={{
          fontFamily: 'var(--font-mono)', fontSize: 9,
          color: 'var(--text-muted)', letterSpacing: '0.04em',
        }}>
          {detail}
        </span>
      )}
    </div>
  );
}
