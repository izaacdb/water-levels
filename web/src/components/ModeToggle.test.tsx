import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ModeToggle } from './ModeToggle'

describe('ModeToggle', () => {
  it('shows the active mode and reports changes', () => {
    const onChange = vi.fn()
    render(<ModeToggle mode="pct" onChange={onChange} />)
    expect(screen.getByRole('radio', { name: '% full' })).toBeChecked()
    fireEvent.click(screen.getByRole('radio', { name: 'vs normal' }))
    expect(onChange).toHaveBeenCalledWith('anom')
  })
})
