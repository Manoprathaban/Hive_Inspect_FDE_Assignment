/**
 * Modal focus handling (FRONTEND_DESIGN §26): move focus into the dialog on open, keep
 * Tab/Shift+Tab inside it, and restore focus to whatever was focused before it opened.
 */

import { useEffect, useRef } from 'react'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ')

function focusable(container: HTMLElement | null): HTMLElement[] {
  return container ? [...container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)] : []
}

export function useModalFocus<T extends HTMLElement>(active = true) {
  const containerRef = useRef<T | null>(null)
  const openerRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!active) return
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    focusable(containerRef.current)[0]?.focus()

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Tab') return
      const container = containerRef.current
      const items = focusable(container)
      if (items.length === 0) return
      const first = items[0]
      const last = items[items.length - 1]
      const current = document.activeElement
      if (event.shiftKey) {
        if (current === first || !container?.contains(current)) {
          event.preventDefault()
          last.focus()
        }
        return
      }
      if (current === last || !container?.contains(current)) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown, true)
    return () => {
      document.removeEventListener('keydown', handleKeyDown, true)
      openerRef.current?.focus()
    }
  }, [active])

  return containerRef
}
