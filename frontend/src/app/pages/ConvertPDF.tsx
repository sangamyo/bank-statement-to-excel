import { useState, useRef, useCallback } from 'react';
import { UploadCard } from '../components/UploadCard';
import { CheckCircle, Download, ArrowLeft } from 'lucide-react';
import { motion } from 'motion/react';
import { toast } from 'sonner';
import { uploadPDF, fetchConversionStatus, downloadFile } from '../services/api';
import { getPreferences } from '../lib/preferences';

export function ConvertPDF() {
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [isConverted, setIsConverted] = useState(false);
  const [convertedFileName, setConvertedFileName] = useState('');
  const [convertedFileId, setConvertedFileId] = useState('');
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const handleConvert = async (file: File) => {
    setIsProcessing(true);
    setProgress(0);
    const xlsxName = file.name.replace(/\.pdf$/i, '') + '.xlsx';
    setConvertedFileName(xlsxName);

    try {
      // Upload the file
      setProgress(20);
      const response = await uploadPDF(file);
      const fileId = response.file.id;
      setConvertedFileId(fileId);
      setProgress(40);

      // Poll for completion
      pollingRef.current = setInterval(async () => {
        try {
          const status = await fetchConversionStatus(fileId);

          if (status.status === 'success') {
            stopPolling();
            setProgress(100);
            setTimeout(() => {
              setIsProcessing(false);
              setIsConverted(true);
              toast.success('Conversion completed successfully!');
              if (getPreferences().autoDownload) {
                downloadFile(fileId, xlsxName).catch(() => toast.error('Automatic download failed.'));
              }
            }, 300);
          } else if (status.status === 'failed') {
            stopPolling();
            setIsProcessing(false);
            setProgress(0);
            toast.error(status.error || 'Conversion failed. The PDF may not contain extractable tables.');
          } else {
            // Still processing – advance progress bar
            setProgress((prev) => Math.min(prev + 5, 90));
          }
        } catch {
          stopPolling();
          setIsProcessing(false);
          setProgress(0);
          toast.error('Error checking conversion status.');
        }
      }, 1500);
    } catch (err) {
      setIsProcessing(false);
      setProgress(0);
      toast.error(err instanceof Error ? err.message : 'Upload failed. Please try again.');
    }
  };

  const handleDownload = async () => {
    if (!convertedFileId) return;
    try {
      await downloadFile(convertedFileId, convertedFileName);
      toast.success(`Downloading ${convertedFileName}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Download failed');
    }
  };

  const handleReset = () => {
    stopPolling();
    setIsConverted(false);
    setProgress(0);
    setConvertedFileName('');
    setConvertedFileId('');
  };

  return (
    <div className="max-w-4xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-2">Convert PDF to Excel</h1>
        <p className="text-gray-400">
          Upload your PDF files and convert them to Excel format in seconds.
        </p>
      </div>

      <div className="grid gap-6">
        {/* Upload Card */}
        <UploadCard
          onConvert={handleConvert}
          isProcessing={isProcessing}
          progress={progress}
        />

        {/* Success Result */}
        {isConverted && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-2xl p-6 border"
            style={{
              background: 'rgba(34, 197, 94, 0.1)',
              borderColor: 'rgba(34, 197, 94, 0.3)',
            }}
          >
            <div className="flex items-start gap-4 mb-6">
              <div
                className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{
                  background: 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)',
                  boxShadow: '0 4px 16px rgba(34, 197, 94, 0.4)',
                }}
              >
                <CheckCircle className="w-6 h-6 text-white" />
              </div>
              <div className="flex-1">
                <h3 className="text-xl font-semibold text-white mb-1">
                  Conversion Successful!
                </h3>
                <p className="text-gray-300 text-sm">
                  Your Excel file is ready to download: <span className="font-medium">{convertedFileName}</span>
                </p>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-3">
              <button
                onClick={handleDownload}
                className="flex-1 flex items-center justify-center gap-2 px-6 py-3 rounded-xl font-semibold transition-all duration-300 hover:scale-[1.02]"
                style={{
                  background: 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)',
                  color: 'white',
                  boxShadow: '0 4px 16px rgba(34, 197, 94, 0.4)',
                }}
              >
                <Download className="w-5 h-5" />
                Download Excel File
              </button>

              <button
                onClick={handleReset}
                className="flex items-center justify-center gap-2 px-6 py-3 rounded-xl font-medium transition-all duration-300 hover:bg-white/10"
                style={{
                  color: '#94a3b8',
                  border: '1px solid rgba(148, 163, 184, 0.3)',
                }}
              >
                <ArrowLeft className="w-5 h-5" />
                Convert Another
              </button>
            </div>
          </motion.div>
        )}

        {/* Info Card */}
        <div
          className="rounded-2xl p-6 border"
          style={{
            background: 'rgba(255, 255, 255, 0.05)',
            borderColor: 'rgba(255, 255, 255, 0.1)',
          }}
        >
          <h3 className="text-lg font-semibold text-white mb-4">How it works</h3>
          <div className="space-y-3">
            {[
              'Upload a text-based bank statement PDF (scanned images are not supported)',
              'The parser detects the column layout, merges multi-line entries and checks running balances',
              'Download an Excel file with Transactions, Summary and Raw Text sheets',
            ].map((step, index) => (
              <div key={index} className="flex items-start gap-3">
                <div
                  className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 text-sm font-semibold"
                  style={{
                    background: 'linear-gradient(135deg, #38bdf8 0%, #0ea5e9 100%)',
                    color: 'white',
                  }}
                >
                  {index + 1}
                </div>
                <p className="text-gray-300 text-sm pt-0.5">{step}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
