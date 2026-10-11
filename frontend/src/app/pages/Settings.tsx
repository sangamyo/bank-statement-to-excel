import { useEffect, useState } from 'react';
import { Download, ShieldCheck, Trash2, Server, KeyRound } from 'lucide-react';
import { toast } from 'sonner';
import {
  Preferences,
  getClientId,
  getPreferences,
  resetClientId,
  savePreferences,
} from '../lib/preferences';
import { HealthResponse, deleteHistory, fetchHealth, fetchHistory } from '../services/api';

const cardStyle = {
  background: 'rgba(255, 255, 255, 0.05)',
  borderColor: 'rgba(255, 255, 255, 0.1)',
};

export function Settings() {
  const [prefs, setPrefs] = useState<Preferences>(getPreferences);
  const [health, setHealth] = useState<HealthResponse | null | undefined>(undefined);
  const [clientId, setClientId] = useState(getClientId);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    fetchHealth().then(setHealth);
  }, []);

  const update = (patch: Partial<Preferences>) => {
    const next = { ...prefs, ...patch };
    setPrefs(next);
    savePreferences(next);
    toast.success('Settings saved');
  };

  const deleteAll = async () => {
    if (!window.confirm('Delete all conversions from this browser, including their files on the server?')) return;
    setIsDeleting(true);
    try {
      const items = await fetchHistory();
      const results = await Promise.allSettled(items.map((item) => deleteHistory(item.id)));
      const failed = results.filter((r) => r.status === 'rejected').length;
      if (failed) toast.error(`${failed} item(s) could not be deleted`);
      else toast.success(`Deleted ${items.length} conversion(s)`);
    } catch {
      toast.error('Could not reach the server');
    } finally {
      setIsDeleting(false);
    }
  };

  const resetId = () => {
    if (!window.confirm('Start a fresh session? Existing conversions stay on the server until they expire, but this browser will no longer see them.')) return;
    setClientId(resetClientId());
    toast.success('New session started');
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-2">Settings</h1>
        <p className="text-gray-400">Preferences are stored in this browser only.</p>
      </div>

      {/* Preferences */}
      <section className="rounded-2xl p-6 border space-y-5" style={cardStyle}>
        <h2 className="text-lg font-semibold text-white">Preferences</h2>
        <Toggle
          icon={Download}
          color="#38bdf8"
          title="Auto-download"
          description="Download the Excel file automatically when a conversion finishes."
          checked={prefs.autoDownload}
          onChange={(v) => update({ autoDownload: v })}
        />
        <Toggle
          icon={Trash2}
          color="#ef4444"
          title="Confirm before deleting"
          description="Ask for confirmation before deleting a conversion."
          checked={prefs.confirmDelete}
          onChange={(v) => update({ confirmDelete: v })}
        />
      </section>

      {/* Privacy */}
      <section className="rounded-2xl p-6 border space-y-4" style={cardStyle}>
        <div className="flex items-center gap-3">
          <ShieldCheck className="w-5 h-5 text-[#22c55e]" />
          <h2 className="text-lg font-semibold text-white">Privacy &amp; data</h2>
        </div>
        <ul className="text-sm text-gray-300 space-y-2 list-disc pl-5">
          <li>Uploaded PDFs are deleted as soon as the conversion finishes.</li>
          <li>
            Converted Excel files and history entries are deleted automatically after{' '}
            <span className="text-white font-medium">
              {health?.retention_hours != null ? `${health.retention_hours} hours` : 'the retention period'}
            </span>
            , or immediately when you delete them.
          </li>
          <li>History is tied to an anonymous ID stored in this browser. Other visitors cannot see your files.</li>
        </ul>
        <div className="flex flex-col sm:flex-row gap-3 pt-2">
          <button
            onClick={deleteAll}
            disabled={isDeleting}
            className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl font-medium text-sm transition-colors disabled:opacity-50"
            style={{ background: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.4)', color: '#fca5a5' }}
          >
            <Trash2 className="w-4 h-4" />
            {isDeleting ? 'Deleting…' : 'Delete all my conversions'}
          </button>
          <button
            onClick={resetId}
            className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl font-medium text-sm transition-colors hover:bg-white/10"
            style={{ border: '1px solid rgba(148, 163, 184, 0.3)', color: '#94a3b8' }}
          >
            <KeyRound className="w-4 h-4" />
            Start a fresh session
          </button>
        </div>
        <p className="text-xs text-gray-500 break-all">Session ID: {clientId}</p>
      </section>

      {/* Server */}
      <section className="rounded-2xl p-6 border" style={cardStyle}>
        <div className="flex items-center gap-3 mb-4">
          <Server className="w-5 h-5 text-[#a855f7]" />
          <h2 className="text-lg font-semibold text-white">Server</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
          <Info
            label="Status"
            value={health === undefined ? 'Checking…' : health ? 'Online' : 'Unreachable'}
            color={health ? '#22c55e' : health === null ? '#ef4444' : undefined}
          />
          <Info label="Max upload size" value={health?.max_upload_mb != null ? `${health.max_upload_mb} MB` : '–'} />
          <Info label="File retention" value={health?.retention_hours != null ? `${health.retention_hours} h` : '–'} />
        </div>
      </section>
    </div>
  );
}

interface ToggleProps {
  icon: React.ElementType;
  color: string;
  title: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}

function Toggle({ icon: Icon, color, title, description, checked, onChange }: ToggleProps) {
  return (
    <label className="flex items-center gap-4 cursor-pointer">
      <div
        className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: `${color}20`, border: `1px solid ${color}40` }}
      >
        <Icon className="w-5 h-5" style={{ color }} />
      </div>
      <div className="flex-1">
        <p className="text-white font-medium">{title}</p>
        <p className="text-sm text-gray-400">{description}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={title}
        onClick={() => onChange(!checked)}
        className="relative w-11 h-6 rounded-full transition-colors flex-shrink-0"
        style={{ background: checked ? '#38bdf8' : 'rgba(148, 163, 184, 0.35)' }}
      >
        <span
          className="absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform"
          style={{ transform: checked ? 'translateX(20px)' : 'translateX(0)' }}
        />
      </button>
    </label>
  );
}

function Info({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <p className="text-gray-400 mb-1">{label}</p>
      <p className="font-medium" style={{ color: color ?? 'white' }}>{value}</p>
    </div>
  );
}
