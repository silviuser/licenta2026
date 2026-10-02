import { useQuery } from '@tanstack/react-query';
import { getNlpInfo } from '../api/nlp';

export function useNlpInfo() {
  return useQuery({
    queryKey: ['nlp', 'info'],
    queryFn: getNlpInfo,
    staleTime: 5 * 60 * 1000, // versions rarely change
    retry: false,
  });
}
