import { useState, useRef } from 'react';
import { Upload, FileText, X, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { toast } from 'sonner';

interface UploadCardProps {
  onConvert: (file: File) => void;
  isProcessing: boolean;
  progress: number;
}

export function UploadCard({ onConvert, isProcessing, progress }: UploadCardProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileSelection(files[0]);
    }
  };

  const handleFileSelection = (file: File) => {
    if (file.type !== 'application/pdf') {
      toast.error('Please select a PDF file');
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      toast.error('File size must be less than 10MB');
      return;
    }

    setSelectedFile(file);
    toast.success('File uploaded successfully');
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFileSelection(files[0]);
    }
  };

  const handleRemoveFile = () => {
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleConvert = () => {
    if (selectedFile) {
      onConvert(selectedFile);
    }
  };

  return (
    <div
      className="rounded-2xl p-6 border"
      style={{
        background: 'rgba(255, 255, 255, 0.05)',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        backdropFilter: 'blur(20px)',
      }}
    >
      <h2 className="text-xl font-semibold text-white mb-4">Upload PDF</h2>

      {/* Upload Zone */}
      <motion.div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !selectedFile && fileInputRef.current?.click()}
        className={`
          relative rounded-xl p-8 border-2 border-dashed transition-all duration-300 cursor-pointer
          ${isDragging ? 'border-[#38bdf8] bg-[#38bdf8]/10 scale-[1.02]' : 'border-gray-600 hover:border-[#38bdf8] hover:bg-white/5'}
          ${selectedFile ? 'cursor-default' : ''}
        `}
        whileHover={!selectedFile ? { scale: 1.01 } : {}}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          onChange={handleFileInputChange}
          className="hidden"
        />

        <AnimatePresence mode="wait">
          {!selectedFile ? (
            <motion.div
              key="upload"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="text-center"
            >
              <div
                className={`inline-flex items-center justify-center w-16 h-16 rounded-full mb-4 transition-all duration-300 ${
                  isDragging ? 'bg-[#38bdf8]/20 scale-110' : 'bg-white/10'
                }`}
              >
                <Upload
                  className={`w-8 h-8 transition-colors duration-300 ${
                    isDragging ? 'text-[#38bdf8]' : 'text-gray-400'
                  }`}
                />
              </div>
              <p className="text-white text-base mb-2">
                Drag and drop your PDF here
              </p>
              <p className="text-gray-400 text-sm mb-4">or</p>
              <button
                className="px-6 py-2.5 rounded-lg font-medium transition-all duration-300 hover:scale-105"
                style={{
                  background: 'linear-gradient(135deg, #38bdf8 0%, #0ea5e9 100%)',
                  color: 'white',
                  boxShadow: '0 4px 16px rgba(56, 189, 248, 0.3)',
                }}
              >
                Choose File
              </button>
              <p className="text-gray-500 text-xs mt-4">
                Maximum file size: 10MB
              </p>
            </motion.div>
          ) : (
            <motion.div
              key="file"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              className="flex items-center justify-between"
            >
              <div className="flex items-center gap-4">
                <div
                  className="w-12 h-12 rounded-lg flex items-center justify-center"
                  style={{
                    background: 'linear-gradient(135deg, #38bdf8 0%, #0ea5e9 100%)',
                  }}
                >
                  <FileText className="w-6 h-6 text-white" />
                </div>
                <div>
                  <p className="text-white font-medium">{selectedFile.name}</p>
                  <p className="text-gray-400 text-sm">
                    {(selectedFile.size / 1024).toFixed(2)} KB
                  </p>
                </div>
              </div>
              {!isProcessing && (
                <button
                  onClick={handleRemoveFile}
                  className="p-2 rounded-lg hover:bg-white/10 transition-colors"
                >
                  <X className="w-5 h-5 text-gray-400 hover:text-white" />
                </button>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      {/* Progress Bar */}
      {isProcessing && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-4"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-400">Converting...</span>
            <span className="text-sm text-[#38bdf8] font-medium">{progress}%</span>
          </div>
          <div
            className="w-full h-2 rounded-full overflow-hidden"
            style={{ background: 'rgba(255, 255, 255, 0.1)' }}
          >
            <motion.div
              className="h-full rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.3 }}
              style={{
                background: 'linear-gradient(90deg, #38bdf8 0%, #0ea5e9 100%)',
                boxShadow: '0 0 10px rgba(56, 189, 248, 0.6)',
              }}
            />
          </div>
        </motion.div>
      )}

      {/* Convert Button */}
      {selectedFile && !isProcessing && (
        <motion.button
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          onClick={handleConvert}
          className="w-full mt-4 py-3 rounded-xl font-semibold transition-all duration-300 hover:scale-[1.02] flex items-center justify-center gap-2"
          style={{
            background: 'linear-gradient(135deg, #38bdf8 0%, #0ea5e9 100%)',
            color: 'white',
            boxShadow: '0 8px 24px rgba(56, 189, 248, 0.4)',
          }}
        >
          Convert to Excel
        </motion.button>
      )}

      {isProcessing && (
        <motion.button
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          disabled
          className="w-full mt-4 py-3 rounded-xl font-semibold flex items-center justify-center gap-2 cursor-not-allowed"
          style={{
            background: 'rgba(100, 116, 139, 0.5)',
            color: 'white',
          }}
        >
          <Loader2 className="w-5 h-5 animate-spin" />
          Processing...
        </motion.button>
      )}
    </div>
  );
}
