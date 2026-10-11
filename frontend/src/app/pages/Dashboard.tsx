import { useState, useEffect } from 'react';
import { FileText, TrendingUp, CheckCircle, Clock, Upload } from 'lucide-react';
import { motion } from 'motion/react';
import { Link } from 'react-router';
import { StatCard } from '../components/StatCard';
import { HistoryTable } from '../components/HistoryTable';
import { ConversionHistory } from '../types';
import { fetchHistory, fetchStats } from '../services/api';

export function Dashboard() {
  const [history, setHistory] = useState<ConversionHistory[]>([]);
  const [stats, setStats] = useState({
    total_conversions: 0,
    success_rate: 0,
    today_count: 0,
    processing_count: 0,
  });

  useEffect(() => {
    const load = async () => {
      try {
        const [historyData, statsData] = await Promise.all([
          fetchHistory(),
          fetchStats(),
        ]);
        // Show only last 5 on dashboard
        setHistory(historyData.slice(0, 5));
        setStats(statsData);
      } catch {
        // Fallback to empty state if backend is down
        setHistory([]);
      }
    };
    load();
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-3xl font-bold text-white mb-2">Dashboard</h1>
        <p className="text-gray-400">
          Welcome back! Here's your conversion overview.
        </p>
      </motion.div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {[
          {
            title: 'Total Conversions',
            value: stats.total_conversions.toLocaleString(),
            icon: FileText,
            color: '#38bdf8',
            trend: undefined,
          },
          {
            title: 'Success Rate',
            value: `${stats.success_rate}%`,
            icon: TrendingUp,
            color: '#22c55e',
            trend: undefined,
          },
          {
            title: 'Completed Today',
            value: stats.today_count.toString(),
            icon: CheckCircle,
            color: '#a855f7',
            trend: undefined,
          },
          {
            title: 'Processing',
            value: stats.processing_count.toString(),
            icon: Clock,
            color: '#f59e0b',
          },
        ].map((stat, index) => (
          <motion.div
            key={stat.title}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
          >
            <StatCard {...stat} />
          </motion.div>
        ))}
      </div>

      {/* Recent Activity */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-white">Recent Activity</h2>
          <Link
            to="/convert"
            className="flex items-center gap-2 px-4 py-2 rounded-xl font-medium transition-all duration-200 hover:scale-105"
            style={{
              background: 'linear-gradient(135deg, #38bdf8 0%, #0ea5e9 100%)',
              color: 'white',
              boxShadow: '0 4px 12px rgba(56, 189, 248, 0.3)',
            }}
          >
            <Upload className="w-4 h-4" />
            Convert New File
          </Link>
        </div>
        <HistoryTable
          data={history}
          onDeleted={(id) => setHistory((prev) => prev.filter((h) => h.id !== id))}
        />
      </motion.div>
    </div>
  );
}