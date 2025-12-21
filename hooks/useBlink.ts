import { useEffect, useRef, useState } from 'react'

/**
 * Hook to detect value changes and trigger a blink animation
 * Returns a ref to attach to the element and a boolean indicating if it's blinking
 */
export function useBlink(value: any, duration: number = 600) {
  const [isBlinking, setIsBlinking] = useState(false)
  const prevValueRef = useRef(value)
  const timeoutRef = useRef<NodeJS.Timeout>()

  useEffect(() => {
    // Check if value has changed
    if (prevValueRef.current !== value) {
      prevValueRef.current = value
      setIsBlinking(true)

      // Clear existing timeout
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }

      // Set timeout to stop blinking
      timeoutRef.current = setTimeout(() => {
        setIsBlinking(false)
      }, duration)
    }

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [value, duration])

  return isBlinking
}

