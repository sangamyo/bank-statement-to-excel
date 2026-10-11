import { useState, useEffect } from 'react';
import { HistoryTable } from '../components/HistoryTable';
import { EmptyState } from '../components/EmptyState';
import { ConversionHistory } from '../types';
import { Search, FileX, RefreshCw } from 'lucide-react';
import { fetchHistory } from '../services/api';
import { toast } from 'sonner';

export function History() {
  const [history, setHistory] = useState<ConversionHistory[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  const loadHistory = async () => {
    try {
      setIsLoading(true);
      const data = await fetchHistory();
      setHistory(data);
    } catch {
      toast.error('Failed to load history. Is the backend running?');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  const filteredHistory = history.filter((item) =>
    item.fileName.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">Conversion History</h1>
          <p className="text-gray-400">
            Conversions from this browser. Files are deleted from the server automatically after the retention period.
          </p>
        </div>

        {/* Stats */}
        <div
          className="flex items-center gap-4 px-6 py-3 rounded-xl"
          style={{
            background: 'rgba(255, 255, 255, 0.05)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
          }}
        >
          <div className="text-center">
            <p className="text-2xl font-bold text-white">{history.length}</p>
            <p className="text-xs text-gray-400">Total</p>
          </div>
          <div className="w-px h-8 bg-white/10" />
          <div className="text-center">
            <p className="text-2xl font-bold text-[#22c55e]">
              {history.filter((h) => h.status === 'success').length}
            </p>
            <p className="text-xs text-gray-400">Success</p>
          </div>
        </div>
      </div>

      {/* Search and Filter */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div
          className="flex-1 flex items-center gap-3 px-4 py-3 rounded-xl"
          style={{
            background: 'rgba(255, 255, 255, 0.05)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
          }}
        >
          <Search className="w-5 h-5 text-gray-400" />
          <input
            type="text"
            placeholder="Search files..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-transparent text-white text-sm outline-none w-full placeholder:text-gray-500"
          />
        </div>

        <button
          onClick={loadHistory}
          className="flex items-center justify-center gap-2 px-6 py-3 rounded-xl font-medium transition-all duration-200 hover:bg-white/10"
          style={{
            border: '1px solid rgba(255, 255, 255, 0.1)',
            color: '#94a3b8',
          }}
        >
          <RefreshCw className="w-5 h-5" />
          <span className="hidden sm:inline">Refresh</span>
        </button>

      </div>

      {/* History Table or Empty State */}
      {isLoading ? (
        <div
          className="rounded-2xl p-12 border text-center"
          style={{
            background: 'rgba(255, 255, 255, 0.05)',
            borderColor: 'rgba(255, 255, 255, 0.1)',
          }}
        >
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full mb-4 animate-pulse" style={{ background: 'rgba(255, 255, 255, 0.1)' }}>
            <RefreshCw className="w-8 h-8 text-gray-400 animate-spin" />
          </div>
          <h3 className="text-xl font-semibold text-white mb-2">Loading history…</h3>
          <p className="text-gray-400">Fetching your conversion records.</p>
        </div>
      ) : filteredHistory.length === 0 ? (
        <EmptyState
          icon={FileX}
          title={searchQuery ? 'No results found' : 'No conversions yet'}
          description={
            searchQuery
              ? `No files match "${searchQuery}". Try a different search term.`
              : 'Your conversion history will appear here once you start converting files.'
          }
        />
      ) : (
        <HistoryTable
          data={filteredHistory}
          onDeleted={(id) => setHistory((prev) => prev.filter((h) => h.id !== id))}
        />
      )}
    </div>
  );
}