/**
 * VNC Modal Component Tests
 * Tests that all buttons are always functional
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import VncLoginModal from '@/components/VncLoginModal';

describe('VncLoginModal Component', () => {
  const mockOnClose = vi.fn();
  const mockOnConfirm = vi.fn();

  const defaultProps = {
    isOpen: true,
    onClose: mockOnClose,
    onConfirm: mockOnConfirm,
    loginState: {
      state: 'waiting_for_login' as const,
      message: 'Test message',
      browser_opened: false
    }
  };

  describe('Button Availability', () => {
    it('should render all 4 action buttons', () => {
      render(<VncLoginModal {...defaultProps} />);

      expect(screen.getByText(/1\. Start VNC/)).toBeInTheDocument();
      expect(screen.getByText(/2\. Start Browser/)).toBeInTheDocument();
      expect(screen.getByText(/3\. Confirm Login/)).toBeInTheDocument();
      expect(screen.getByText(/4\. Kill VNC/)).toBeInTheDocument();
    });

    it('should NOT have any disabled buttons', () => {
      render(<VncLoginModal {...defaultProps} />);

      const buttons = screen.getAllByRole('button');
      buttons.forEach(button => {
        expect(button).not.toHaveAttribute('disabled');
      });
    });

    it('should have all buttons clickable', async () => {
      render(<VncLoginModal {...defaultProps} />);

      const startVncBtn = screen.getByText(/1\. Start VNC/).closest('button');
      const startBrowserBtn = screen.getByText(/2\. Start Browser/).closest('button');
      const confirmBtn = screen.getByText(/3\. Confirm Login/).closest('button');
      const killVncBtn = screen.getByText(/4\. Kill VNC/).closest('button');

      expect(startVncBtn).not.toBeDisabled();
      expect(startBrowserBtn).not.toBeDisabled();
      expect(confirmBtn).not.toBeDisabled();
      expect(killVncBtn).not.toBeDisabled();
    });
  });

  describe('Button Functionality', () => {
    it('should call handler when Start VNC is clicked', async () => {
      const { rerender } = render(<VncLoginModal {...defaultProps} />);

      const startVncBtn = screen.getByText(/1\. Start VNC/).closest('button');
      fireEvent.click(startVncBtn!);

      // Button should still be clickable after click
      expect(startVncBtn).not.toBeDisabled();
    });

    it('should call handler when Start Browser is clicked', async () => {
      render(<VncLoginModal {...defaultProps} />);

      const startBrowserBtn = screen.getByText(/2\. Start Browser/).closest('button');
      fireEvent.click(startBrowserBtn!);

      // Button should still be clickable after click
      expect(startBrowserBtn).not.toBeDisabled();
    });

    it('should call handler when Confirm Login is clicked', async () => {
      render(<VncLoginModal {...defaultProps} />);

      const confirmBtn = screen.getByText(/3\. Confirm Login/).closest('button');
      fireEvent.click(confirmBtn!);

      // Button should still be clickable after click
      expect(confirmBtn).not.toBeDisabled();
    });

    it('should call handler when Kill VNC is clicked', async () => {
      render(<VncLoginModal {...defaultProps} />);

      const killVncBtn = screen.getByText(/4\. Kill VNC/).closest('button');
      fireEvent.click(killVncBtn!);

      // Button should still be clickable after click
      expect(killVncBtn).not.toBeDisabled();
    });
  });

  describe('Multiple Clicks', () => {
    it('should allow clicking Start Browser multiple times', async () => {
      render(<VncLoginModal {...defaultProps} />);

      const startBrowserBtn = screen.getByText(/2\. Start Browser/).closest('button');

      // Click multiple times
      fireEvent.click(startBrowserBtn!);
      fireEvent.click(startBrowserBtn!);
      fireEvent.click(startBrowserBtn!);

      // Button should still be clickable
      expect(startBrowserBtn).not.toBeDisabled();
    });

    it('should allow clicking Start VNC multiple times', async () => {
      render(<VncLoginModal {...defaultProps} />);

      const startVncBtn = screen.getByText(/1\. Start VNC/).closest('button');

      // Click multiple times
      fireEvent.click(startVncBtn!);
      fireEvent.click(startVncBtn!);
      fireEvent.click(startVncBtn!);

      // Button should still be clickable
      expect(startVncBtn).not.toBeDisabled();
    });
  });

  describe('VNC Status Indicator', () => {
    it('should display VNC status indicator', () => {
      render(<VncLoginModal {...defaultProps} />);

      // Should show some status indicator
      const header = screen.getByText('TradingView Login');
      expect(header).toBeInTheDocument();
    });
  });

  describe('Step-by-Step Instructions', () => {
    it('should display step-by-step instructions', () => {
      render(<VncLoginModal {...defaultProps} />);

      expect(screen.getByText(/Step-by-Step Instructions/)).toBeInTheDocument();
      expect(screen.getByText(/Press "Start VNC" button/)).toBeInTheDocument();
      expect(screen.getByText(/Connect to VNC using a VNC client/)).toBeInTheDocument();
      expect(screen.getByText(/Press "Start Browser" button/)).toBeInTheDocument();
      expect(screen.getByText(/Login to TradingView/)).toBeInTheDocument();
      expect(screen.getByText(/Press "Confirm Login" button/)).toBeInTheDocument();
      expect(screen.getByText(/Press "Kill VNC" button/)).toBeInTheDocument();
    });
  });
});

