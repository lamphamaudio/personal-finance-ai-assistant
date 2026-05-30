import { useState, useCallback } from 'react';
import { uploadFileRaw } from '../api/services';

export const useFileUploader = () => {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [step, setStep] = useState('');
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const reset = useCallback(() => {
    setUploading(false);
    setProgress(0);
    setStep('');
    setError(null);
    setResult(null);
  }, []);

  const uploadFile = useCallback(async (file) => {
    setUploading(true);
    setProgress(0);
    setStep('Connecting...');
    setError(null);
    setResult(null);

    try {
      const response = await uploadFileRaw(file);

      if (!response.ok || !response.body) {
        throw new Error(`Server error: ${response.status} ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        
        // SSE events are separated by \n\n
        const parts = buffer.split('\n\n');
        buffer = parts.pop(); // Keep incomplete trailing chunk

        for (const part of parts) {
          const dataLine = part.split('\n').find(l => l.startsWith('data: '));
          if (!dataLine) continue;

          let event;
          try {
            event = JSON.parse(dataLine.slice(6));
          } catch {
            continue;
          }

          if (event.error) {
            throw new Error(event.step || 'An error occurred during import processing.');
          }

          if (event.pct !== undefined) {
            setProgress(event.pct);
          }
          if (event.step !== undefined) {
            setStep(event.step);
          }

          if (event.done) {
            setUploading(false);
            if (!event.transactions || event.transactions.length === 0) {
              throw new Error(event.message || 'All transactions in this file are duplicates and have already been imported.');
            }
            setResult({
              transactions: event.transactions.map(item => ({
                ...item,
                apply_to_future: item.apply_to_future !== false,
              })),
              message: event.message
            });
            return;
          }
        }
      }
    } catch (err) {
      console.error('File upload stream parsing error:', err);
      setError(err.message || 'Upload failed due to connection issues.');
      setUploading(false);
    }
  }, []);

  return {
    uploading,
    progress,
    step,
    error,
    result,
    uploadFile,
    reset
  };
};
