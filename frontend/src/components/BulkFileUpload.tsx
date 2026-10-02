import { useRef, useState } from 'react';
import type { DragEvent } from 'react';
import { Upload } from 'lucide-react';
import { Box, Button, CircularProgress, Stack, Typography } from '@mui/material';
import { MAX_PDF_BYTES, PDF_MIME } from '../lib/constants';
import { formatBytes } from '../lib/formatters';

interface BulkFileUploadProps {
  uploading: boolean;
  onFiles: (files: File[]) => void;
  label?: string;
}

/** Drag & drop / pick multiple PDFs (REWORK 1 D21). Client-side PDF + size guard. */
export function BulkFileUpload({ uploading, onFiles, label = 'Upload CVs' }: BulkFileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  function validateAndSend(fileList: FileList | null | undefined) {
    setLocalError(null);
    const files = fileList ? Array.from(fileList) : [];
    if (files.length === 0) {
      setLocalError('No files selected. Choose one or more PDFs to upload.');
      return;
    }
    const nonPdf = files.find((f) => f.type !== PDF_MIME);
    if (nonPdf) {
      setLocalError(`"${nonPdf.name}" isn't a PDF. Please upload PDF résumés only.`);
      return;
    }
    const tooLarge = files.find((f) => f.size > MAX_PDF_BYTES);
    if (tooLarge) {
      setLocalError(
        `"${tooLarge.name}" is too large (${formatBytes(tooLarge.size)}). Max ${formatBytes(MAX_PDF_BYTES)}.`,
      );
      return;
    }
    onFiles(files);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    if (uploading) return;
    validateAndSend(e.dataTransfer.files);
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
            Drag &amp; drop PDF résumés here, or
          </Typography>
          <Button
            variant="contained"
            startIcon={uploading ? <CircularProgress size={16} color="inherit" /> : <Upload size={16} />}
            disabled={uploading}
            onClick={() => inputRef.current?.click()}
          >
            {uploading ? 'Uploading…' : label}
          </Button>
          <Typography variant="caption" color="text.secondary">
            PDF only · multiple allowed · up to {formatBytes(MAX_PDF_BYTES)} each
          </Typography>
        </Stack>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          multiple
          hidden
          onChange={(e) => {
            validateAndSend(e.target.files);
            e.target.value = '';
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
