'use client';

import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle } from 'lucide-react';

interface PauseState {
  is_paused: boolean;
  pause_reason?: string;
  error_message?: string;
  user_confirmed: boolean;
}

interface OpenAIRateLimitBannerProps {
  instanceId: string;
}

export function OpenAIRateLimitBanner({ instanceId }: OpenAIRateLimitBannerProps) {
  const [pauseState, setPauseState] = useState<PauseState | null>(null);
  const [isConfirming, setIsConfirming] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);

  // Poll pause state every 5 seconds
  useEffect(() => {
    const checkPauseState = async () => {
      try {
        const response = await fetch(
          `/api/bot/pause-state?instance_id=${instanceId}`
        );
        const data = await response.json();
        setPauseState(data);
      } catch (error) {
        console.error('Failed to check pause state:', error);
      }
    };

    checkPauseState();
    const interval = setInterval(checkPauseState, 5000);
    return () => clearInterval(interval);
  }, [instanceId]);

  const handleConfirmRecharge = async () => {
    setIsConfirming(true);
    try {
      const response = await fetch(
        `/api/bot/pause-state?instance_id=${instanceId}&action=confirm`,
        { method: 'POST' }
      );

      if (response.ok) {
        setShowSuccess(true);
        setTimeout(() => {
          setShowSuccess(false);
          setPauseState(null);
        }, 3000);
      }
    } catch (error) {
      console.error('Failed to confirm recharge:', error);
    } finally {
      setIsConfirming(false);
    }
  };

  // Don't show banner if not paused
  if (!pauseState?.is_paused) {
    return null;
  }

  // Show success message
  if (showSuccess) {
    return (
      <div className="fixed top-0 left-0 right-0 z-50 bg-green-50 border-b border-green-200 px-4 py-3">
        <div className="max-w-7xl mx-auto flex items-center gap-3">
          <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-medium text-green-800">
              ✅ Recharge confirmed! Bot is resuming...
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Show pause banner
  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-red-50 border-b-2 border-red-500 px-4 py-4">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-6 h-6 text-red-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <h3 className="font-semibold text-red-900 mb-1">
              🛑 Bot Paused - OpenAI Rate Limit Exceeded
            </h3>
            <p className="text-sm text-red-800 mb-3">
              {pauseState.error_message ||
                'OpenAI API rate limit (429) detected. Please recharge your OpenAI credits and confirm below.'}
            </p>
            <button
              onClick={handleConfirmRecharge}
              disabled={isConfirming}
              className="inline-flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-medium rounded-md transition-colors"
            >
              {isConfirming ? (
                <>
                  <span className="inline-block animate-spin">⏳</span>
                  Confirming...
                </>
              ) : (
                <>
                  <CheckCircle className="w-4 h-4" />
                  Confirm Recharge & Resume
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

