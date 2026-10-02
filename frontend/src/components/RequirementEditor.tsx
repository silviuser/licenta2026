import { Trash2 } from 'lucide-react';
import {
  Box,
  Button,
  IconButton,
  MenuItem,
  Slider,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import type { Importance, RequirementInput } from '../api/types';
import { CTA } from '../lib/constants';
import { emptyRequirement } from '../lib/requirements';

interface RequirementEditorProps {
  value: RequirementInput[];
  onChange: (rows: RequirementInput[]) => void;
  /** When true, the list may be emptied entirely (e.g. auto-extract flow, D18). */
  allowEmpty?: boolean;
}

/** Editable list of requirement rows (§14.2). */
export function RequirementEditor({ value, onChange, allowEmpty = false }: RequirementEditorProps) {
  const minRows = allowEmpty ? 0 : 1;

  function update(index: number, patch: Partial<RequirementInput>) {
    onChange(value.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function remove(index: number) {
    if (value.length <= minRows) return;
    onChange(value.filter((_, i) => i !== index));
  }

  function add() {
    onChange([...value, emptyRequirement()]);
  }

  return (
    <Stack spacing={2}>
      {value.map((row, i) => (
        <Box
          key={i}
          sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 2, bgcolor: 'background.paper' }}
        >
          <Stack spacing={2}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start">
              <TextField
                label="Requirement"
                value={row.text}
                onChange={(e) => update(i, { text: e.target.value })}
                fullWidth
                required
                error={row.text.trim().length === 0}
                placeholder="e.g. 3+ years of TypeScript"
              />
              <TextField
                select
                label="Importance"
                value={row.importance}
                onChange={(e) => update(i, { importance: e.target.value as Importance })}
                sx={{ minWidth: 160 }}
              >
                <MenuItem value="required">Required</MenuItem>
                <MenuItem value="nice_to_have">Nice-to-have</MenuItem>
              </TextField>
            </Stack>

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="center">
              <TextField
                label="Skill label (optional)"
                value={row.skillLabel ?? ''}
                onChange={(e) => update(i, { skillLabel: e.target.value || null })}
                fullWidth
                placeholder="e.g. TypeScript"
              />
              <Box sx={{ width: { xs: '100%', sm: 220 }, px: 1 }}>
                <Typography variant="caption" color="text.secondary" gutterBottom>
                  Confidence: {(row.confidence ?? 0.5).toFixed(2)}
                </Typography>
                <Slider
                  value={row.confidence ?? 0.5}
                  onChange={(_, v) => update(i, { confidence: v as number })}
                  min={0}
                  max={1}
                  step={0.05}
                  size="small"
                  aria-label="Confidence"
                />
              </Box>
              <Tooltip title={value.length <= minRows ? 'At least one requirement is needed' : 'Remove'}>
                <span>
                  <IconButton
                    aria-label="Remove requirement"
                    onClick={() => remove(i)}
                    disabled={value.length <= minRows}
                    color="error"
                  >
                    <Trash2 size={18} />
                  </IconButton>
                </span>
              </Tooltip>
            </Stack>
          </Stack>
        </Box>
      ))}

      <Box>
        <Button onClick={add} variant="outlined">
          {CTA.addRequirement}
        </Button>
      </Box>
    </Stack>
  );
}
