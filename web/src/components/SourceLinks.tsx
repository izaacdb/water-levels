import type { SourceInfo } from '../contract'

/** Links to each official source behind a figure, comma-separated. */
export function SourceLinks({ sources }: { sources: SourceInfo[] }) {
  return (
    <>
      {sources.map((source, i) => (
        <span key={source.id}>
          {i > 0 && ', '}
          <a href={source.url} target="_blank" rel="noreferrer">
            {source.name}
          </a>
        </span>
      ))}
    </>
  )
}
