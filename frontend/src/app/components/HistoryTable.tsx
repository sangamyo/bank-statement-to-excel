import { useState } from 'react';
import { Download, CheckCircle, XCircle, Loader2, Trash2 } from 'lucide-react';
import { motion } from 'motion/react';
import { ConversionHistory } from '../types';
import { toast } from 'sonner';
import { deleteHistory, downloadFile } from '../services/api';
import { getPreferences } from '../lib/preferences';

interface HistoryTableProps {
  data: ConversionHistory[];
  onDeleted?: (id: string) => void;
}

export function HistoryTable({ data, onDeleted }: HistoryTableProps) {
  const [busyId, setBusyId] = useState<string | null>(null);

  const handleDownload = async (item: ConversionHistory) => {
    if (item.status !== 'success') return;
    try {
      await downloadFile(item.id, item.fileName.replace(/\.pdf$/i, '') + '.xlsx');
      toast.success(`Downloading ${item.fileName}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Download failed');
    }
  };

  const handleDelete = async (item: ConversionHistory) => {
    if (getPreferences().confirmDelete && !window.confirm(`Delete "${item.fileName}" and its Excel file from the server?`)) {
      return;
    }
    try {
      setBusyId(item.id);
      await deleteHistory(item.id);
      toast.success('Conversion deleted');
      onDeleted?.(item.id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setBusyId(null);
    }
  };

  const getStatusIcon = (status: ConversionHistory['status']) => {
    switch (status) {
      case 'success':
        return <CheckCircle className="w-5 h-5 text-[#22c55e]" />;
      case 'failed':
        return <XCircle className="w-5 h-5 text-[#ef4444]" />;
      case 'processing':
        return <Loader2 className="w-5 h-5 text-[#38bdf8] animate-spin" />;
    }
  };

  const getStatusBadge = (status: ConversionHistory['status']) => {
    const styles = {
      success: {
        background: 'rgba(34, 197, 94, 0.1)',
        border: '1px solid rgba(34, 197, 94, 0.3)',
        color: '#22c55e',
      },
      failed: {
        background: 'rgba(239, 68, 68, 0.1)',
        border: '1px solid rgba(239, 68, 68, 0.3)',
        color: '#ef4444',
      },
      processing: {
        background: 'rgba(56, 189, 248, 0.1)',
        border: '1px solid rgba(56, 189, 248, 0.3)',
        color: '#38bdf8',
      },
    };

    return (
      <span
        className="inline-flex items-center gap-2 px-3 py-1 rounded-lg text-sm font-medium"
        style={styles[status]}
      >
        {getStatusIcon(status)}
        {status.charAt(0).toUpperCase() + status.slice(1)}
      </span>
    );
  };

  if (data.length === 0) {
    return (
      <div
        className="rounded-2xl p-12 border text-center"
        style={{
          background: 'rgba(255, 255, 255, 0.05)',
          borderColor: 'rgba(255, 255, 255, 0.1)',
        }}
      >
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full mb-4" style={{ background: 'rgba(255, 255, 255, 0.1)' }}>
          <Download className="w-8 h-8 text-gray-400" />
        </div>
        <h3 className="text-xl font-semibold text-white mb-2">No conversions yet</h3>
        <p className="text-gray-400">
          Your conversion history will appear here once you start converting files.
        </p>
      </div>
    );
  }

  return (
    <div
      className="rounded-2xl border overflow-hidden"
      style={{
        background: 'rgba(255, 255, 255, 0.05)',
        borderColor: 'rgba(255, 255, 255, 0.1)',
      }}
    >
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr
              className="border-b"
              style={{
                background: 'rgba(255, 255, 255, 0.03)',
                borderColor: 'rgba(255, 255, 255, 0.1)',
              }}
            >
              <th className="px-6 py-4 text-left text-sm font-semibold text-gray-400">
                File Name
              </th>
              <th className="px-6 py-4 text-left text-sm font-semibold text-gray-400">
                Date
              </th>
              <th className="px-6 py-4 text-left text-sm font-semibold text-gray-400">
                Size
              </th>
              <th className="px-6 py-4 text-left text-sm font-semibold text-gray-400">
                Status
              </th>
              <th className="px-6 py-4 text-right text-sm font-semibold text-gray-400">
                Action
              </th>
            </tr>
          </thead>
          <tbody>
            {data.map((item, index) => (
              <motion.tr
                key={item.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
                className="border-b border-white/5 hover:bg-white/5 transition-colors"
              >
                <td className="px-6 py-4">
                  <div className="flex items-center gap-3">
                    <div
                      className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
                      style={{
                        background: 'rgba(56, 189, 248, 0.1)',
                        border: '1px solid rgba(56, 189, 248, 0.2)',
                      }}
                    >
                      <Download className="w-5 h-5 text-[#38bdf8]" />
                    </div>
                    <span className="text-white font-medium truncate max-w-xs">
                      {item.fileName}
                    </span>
                  </div>
                </td>
                <td className="px-6 py-4 text-gray-400 text-sm">{item.date}</td>
                <td className="px-6 py-4 text-gray-400 text-sm">{item.fileSize}</td>
                <td className="px-6 py-4">{getStatusBadge(item.status)}</td>
                <td className="px-6 py-4 text-right whitespace-nowrap">
                  <button
                    onClick={() => handleDownload(item)}
                    disabled={item.status !== 'success'}
                    className={`
                      inline-flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm
                      transition-all duration-200
                      ${
                        item.status === 'success'
                          ? 'hover:scale-105'
                          : 'opacity-50 cursor-not-allowed'
                      }
                    `}
                    style={
                      item.status === 'success'
                        ? {
                            background: 'linear-gradient(135deg, #38bdf8 0%, #0ea5e9 100%)',
                            color: 'white',
                            boxShadow: '0 4px 12px rgba(56, 189, 248, 0.3)',
                          }
                        : {
                            background: 'rgba(100, 116, 139, 0.3)',
                            color: 'rgba(255, 255, 255, 0.5)',
                          }
                    }
                  >
                    <Download className="w-4 h-4" />
                    Download
                  </button>
                  {onDeleted && (
                    <button
                      onClick={() => handleDelete(item)}
                      disabled={busyId === item.id || item.status === 'processing'}
                      aria-label={`Delete ${item.fileName}`}
                      title="Delete from server"
                      className="ml-2 inline-flex items-center justify-center p-2 rounded-lg text-gray-400 transition-colors hover:text-[#ef4444] hover:bg-white/5 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </td>
              </motion.tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
