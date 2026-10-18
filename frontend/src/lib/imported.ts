/** What an import or sync hands the account page (as router state), so it can confirm what just happened. */
export interface ImportedState {
  imported: { title: string; detail: string }
}

const plural = (count: number, noun: string) => `${count} ${noun}${count === 1 ? '' : 's'}`

/** `elsewhere`: what the same import put into other accounts, mentioned on the account page it lands on. */
export function importedState(
  source: string,
  imported: number,
  duplicates: number,
  elsewhere: { name: string; imported: number }[] = [],
): ImportedState {
  const also = elsewhere.length
    ? `Also ${elsewhere.map((part) => `${plural(part.imported, 'transaction')} into ${part.name}`).join(', ')}.`
    : ''
  const skipped = duplicates ? `${plural(duplicates, 'transaction')} already recorded and skipped.` : 'No duplicates found.'
  return {
    imported: {
      title: imported ? `${source}: ${plural(imported, 'new transaction')}` : `${source}: nothing new`,
      detail: [also, skipped].filter(Boolean).join(' '),
    },
  }
}

export function readImportedState(state: unknown): ImportedState['imported'] | null {
  if (typeof state !== 'object' || state === null || !('imported' in state)) return null
  return (state as ImportedState).imported
}
