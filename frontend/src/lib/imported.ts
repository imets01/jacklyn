/** What an import or sync hands the account page (as router state), so it can confirm what just happened. */
export interface ImportedState {
  imported: { title: string; detail: string }
}

const plural = (count: number, noun: string) => `${count} ${noun}${count === 1 ? '' : 's'}`

export function importedState(source: string, imported: number, duplicates: number): ImportedState {
  return {
    imported: {
      title: imported ? `${source}: ${plural(imported, 'new transaction')}` : `${source}: nothing new`,
      detail: duplicates ? `${plural(duplicates, 'transaction')} already recorded and skipped.` : 'No duplicates found.',
    },
  }
}

export function readImportedState(state: unknown): ImportedState['imported'] | null {
  if (typeof state !== 'object' || state === null || !('imported' in state)) return null
  return (state as ImportedState).imported
}
