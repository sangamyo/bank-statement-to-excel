export interface ConversionHistory {
  id: string;
  fileName: string;
  date: string;
  status: 'success' | 'failed' | 'processing';
  fileSize: string;
  downloadUrl?: string;
  error?: string;
}

export interface User {
  name: string;
  email: string;
  avatar: string;
}
