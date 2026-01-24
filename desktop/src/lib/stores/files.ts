import { writable, derived } from 'svelte/store';

export const selectedPaths = writable<string[]>([]);
export const folderFiles = writable<string[]>([]);
export const showFileSelector = writable(false);
export const currentFolder = writable<string | null>(null);
export const pendingSelection = writable<Set<string>>(new Set());

// Derived store for file count display
export const selectedFilesCount = derived(selectedPaths, ($paths) => $paths.length);

// Derived store for pending selection count
export const pendingSelectionCount = derived(
	pendingSelection,
	($pending) => $pending.size
);

// Reset all file state
export function resetFiles() {
	selectedPaths.set([]);
	folderFiles.set([]);
	showFileSelector.set(false);
	currentFolder.set(null);
	pendingSelection.set(new Set());
}
