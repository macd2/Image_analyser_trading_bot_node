'use client';

import React, { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { AlertCircle, CheckCircle, Loader2 } from 'lucide-react';

interface TradeReplayModalProps {
  tradeId: string;
  isOpen: boolean;
  onClose: () => void;
}

interface ReplayResult {
  trade_id: string;
  is_reproducible: boolean;
  similarity_score: number;
  differences: Array<{
    field: string;
    original: any;
    replayed: any;
  }>;
  original_recommendation: Record<string, any>;
  replayed_recommendation: Record<string, any>;
  error?: string;
}

export function TradeReplayModal({ tradeId, isOpen, onClose }: TradeReplayModalProps) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ReplayResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleReplay = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(`/api/bot/trades/${tradeId}/replay-analysis`, {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error(`Failed to replay trade: ${response.statusText}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setResult(null);
    setError(null);
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Trade Reproducibility Replay</DialogTitle>
          <DialogDescription>
            Replay this trade with identical inputs to verify reproducibility
          </DialogDescription>
        </DialogHeader>

        {!result && !error && (
          <div className="space-y-4">
            <p className="text-sm text-gray-600">
              This will re-run the analysis with the exact same inputs that were used when this trade was created.
              If the results match, the trade is fully reproducible.
            </p>
            <Button
              onClick={handleReplay}
              disabled={loading}
              className="w-full"
            >
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Replaying...
                </>
              ) : (
                'Start Replay'
              )}
            </Button>
          </div>
        )}

        {error && (
          <div className="space-y-4">
            <div className="flex items-start gap-3 p-4 bg-red-50 border border-red-200 rounded-lg">
              <AlertCircle className="h-5 w-5 text-red-600 mt-0.5 flex-shrink-0" />
              <div>
                <h3 className="font-semibold text-red-900">Replay Failed</h3>
                <p className="text-sm text-red-700 mt-1">{error}</p>
              </div>
            </div>
            <Button onClick={handleReplay} variant="outline" className="w-full">
              Try Again
            </Button>
          </div>
        )}

        {result && (
          <div className="space-y-6">
            {/* Reproducibility Status */}
            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
              <div className="flex items-center gap-3">
                {result.is_reproducible ? (
                  <>
                    <CheckCircle className="h-6 w-6 text-green-600" />
                    <div>
                      <h3 className="font-semibold text-green-900">Reproducible</h3>
                      <p className="text-sm text-green-700">Trade can be replayed with identical results</p>
                    </div>
                  </>
                ) : (
                  <>
                    <AlertCircle className="h-6 w-6 text-yellow-600" />
                    <div>
                      <h3 className="font-semibold text-yellow-900">Not Fully Reproducible</h3>
                      <p className="text-sm text-yellow-700">Some differences detected</p>
                    </div>
                  </>
                )}
              </div>
              <Badge variant={result.is_reproducible ? 'default' : 'secondary'}>
                {result.similarity_score.toFixed(1)}% Match
              </Badge>
            </div>

            {/* Differences */}
            {result.differences.length > 0 && (
              <div className="space-y-3">
                <h3 className="font-semibold">Differences Found</h3>
                <div className="space-y-2">
                  {result.differences.map((diff, idx) => (
                    <div key={idx} className="p-3 bg-yellow-50 border border-yellow-200 rounded">
                      <p className="font-medium text-sm text-yellow-900">{diff.field}</p>
                      <div className="grid grid-cols-2 gap-2 mt-2 text-xs">
                        <div>
                          <p className="text-gray-600">Original:</p>
                          <p className="font-mono text-gray-900">{JSON.stringify(diff.original)}</p>
                        </div>
                        <div>
                          <p className="text-gray-600">Replayed:</p>
                          <p className="font-mono text-gray-900">{JSON.stringify(diff.replayed)}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Recommendations */}
            <div className="space-y-3">
              <h3 className="font-semibold">Comparison Details</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="p-3 bg-blue-50 rounded">
                  <p className="text-gray-600">Original Confidence</p>
                  <p className="font-mono font-semibold">{result.original_recommendation.confidence?.toFixed(2)}</p>
                </div>
                <div className="p-3 bg-blue-50 rounded">
                  <p className="text-gray-600">Replayed Confidence</p>
                  <p className="font-mono font-semibold">{result.replayed_recommendation.confidence?.toFixed(2)}</p>
                </div>
              </div>
            </div>

            <Button onClick={handleReplay} variant="outline" className="w-full">
              Run Replay Again
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

