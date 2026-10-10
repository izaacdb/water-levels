import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Legend } from './Legend'

describe('Legend', () => {
  it('describes % full in pct mode', () => {
    render(<Legend mode="pct" />)
    expect(screen.getByText(/% full/)).toBeInTheDocument()
    expect(screen.getByText('80–100%')).toBeInTheDocument()
    expect(screen.queryByText(/insufficient history/i)).not.toBeInTheDocument()
  })

  it('describes the anomaly and insufficient history in vs-normal mode', () => {
    render(<Legend mode="anom" />)
    expect(screen.getByText(/vs normal for this week/i)).toBeInTheDocument()
    expect(screen.getByText('Near normal')).toBeInTheDocument()
    expect(screen.getByText(/insufficient history/i)).toBeInTheDocument()
  })
})
