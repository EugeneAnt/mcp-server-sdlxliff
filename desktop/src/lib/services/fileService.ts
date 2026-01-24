import { get } from 'svelte/store';
import { selectSdlxliffFile, selectFolder, findSdlxliffFiles } from '$lib/file-picker';
import {
	selectedPaths,
	folderFiles,
	showFileSelector,
	currentFolder,
	pendingSelection,
	resetFiles
} from '$lib/stores/files';
import { indexFile, ragInitialized } from '$lib/services/ragService';
import { ragEnabled } from '$lib/stores/settings';

// Helper to index files for RAG (non-blocking)
async function indexFilesForRag(paths: string[]): Promise<void> {
	if (!get(ragEnabled) || !get(ragInitialized)) return;

	for (const path of paths) {
		try {
			await indexFile(path);
		} catch (error) {
			console.warn('RAG indexing failed for:', path, error);
		}
	}
}

export async function handleSelectFile(): Promise<void> {
	const path = await selectSdlxliffFile();
	if (path) {
		selectedPaths.set([path]);
		folderFiles.set([]);
		showFileSelector.set(false);
		currentFolder.set(null);
		pendingSelection.set(new Set());

		// Index for RAG (non-blocking)
		indexFilesForRag([path]);
	}
}

export async function handleSelectFolder(): Promise<void> {
	const path = await selectFolder();
	if (path) {
		currentFolder.set(path);
		const files = await findSdlxliffFiles(path);

		if (files.length === 0) {
			alert('No .sdlxliff files found in this folder.');
			return;
		} else if (files.length === 1) {
			selectedPaths.set([files[0]]);
			folderFiles.set([]);
			showFileSelector.set(false);

			// Index for RAG (non-blocking)
			indexFilesForRag([files[0]]);
		} else {
			folderFiles.set(files);
			showFileSelector.set(true);
			pendingSelection.set(new Set());
		}
	}
}

export function toggleFileSelection(filePath: string): void {
	pendingSelection.update((selection) => {
		const newSelection = new Set(selection);
		if (newSelection.has(filePath)) {
			newSelection.delete(filePath);
		} else {
			newSelection.add(filePath);
		}
		return newSelection;
	});
}

export function confirmFileSelection(): void {
	const pending = get(pendingSelection);
	if (pending.size > 0) {
		const paths = Array.from(pending).sort();
		selectedPaths.set(paths);
		showFileSelector.set(false);
		pendingSelection.set(new Set());

		// Index for RAG (non-blocking)
		indexFilesForRag(paths);
	}
}

export function selectAllFiles(): void {
	const files = get(folderFiles);
	pendingSelection.set(new Set(files));
}

export function clearSelectedPath(): void {
	resetFiles();
}
