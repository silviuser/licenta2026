import { useRef, useState } from 'react';
import type { DragEvent } from 'react';
import { Upload } from 'lucide-react';
import { Box, Button, CircularProgress, Stack, Typography } from '@mui/material';
import { CTA, MAX_PDF_BYTES, PDF_MIME } from '../lib/constants';
import { formatBytes } from '../lib/formatters';

interface FileUploadProps {
  uploading: boolean;
  onFile: (file: File) => void;
}

/** Dropzone + button. Client-side PDF + size guard (§14.2). */
export function FileUpload({ uploading, onFile }: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  function validateAndSend(file: File | undefined) {
    setLocalError(null);
    if (!file) {
      setLocalError('No file selected. Choose a PDF to upload.');
      return;
    }
    if (file.type !== PDF_MIME) {
      setLocalError("That file isn't a PDF. Please upload a PDF résumé.");
      return;
    }
    if (file.size > MAX_PDF_BYTES) {
      setLocalError(
        `This file is too large (${formatBytes(file.size)}). Upload a PDF under ${formatBytes(MAX_PDF_BYTES)}.`,
      );
      return;
    }
    onFile(file);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    if (uploading) return;
    validateAndSend(e.dataTransfer.files?.[0]);
  }

  return (
    <Box>
      <Box
        onDragOver={(e) => {
          e.preventDefault();
          if (!uploading) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        sx={{
          border: 2,
          borderStyle: 'dashed',
          borderColor: dragOver ? 'primary.main' : 'divider',
          borderRadius: 1,
          bgcolor: dragOver ? 'action.hover' : 'background.paper',
          p: 4,
          textAlign: 'center',
          transition: 'border-color 150ms, background-color 150ms',
        }}
      >
        <Stack spacing={1.5} alignItems="center">
          <Upload size={32} strokeWidth={1.75} style={{ opacity: 0.5 }} />
          <Typography variant="body2" color="text.secondary">
            Drag &amp; drop a PDF résumé here, or
          </Typography>
          <Button
            variant="contained"
            startIcon={uploading ? <CircularProgress size={16} color="inherit" /> : <Upload size={16} />}
            disabled={uploading}
            onClick={() => inputRef.current?.click()}
          >
            {uploading ? 'Uploading…' : CTA.uploadCv}
          </Button>
          <Typography variant="caption" color="text.secondary">
            PDF only · up to {formatBytes(MAX_PDF_BYTES)}
          </Typography>
        </Stack>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          hidden
          onChange={(e) => {
            validateAndSend(e.target.files?.[0]);
            e.target.value = ''; // allow re-selecting the same file
          }}
        />
      </Box>
      {localError && (
        <Typography variant="body2" color="error.main" sx={{ mt: 1 }}>
          {localError}
        </Typography>
      )}
    </Box>
  );
}
