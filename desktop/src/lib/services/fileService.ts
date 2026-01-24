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

export async function handleSelectFile(): Promise<void> {
	const path = await selectSdlxliffFile();
	if (path) {
		selectedPaths.set([path]);
		folderFiles.set([]);
		showFileSelector.set(false);
		currentFolder.set(null);
		pendingSelection.set(new Set());
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
		selectedPaths.set(Array.from(pending).sort());
		showFileSelector.set(false);
		pendingSelection.set(new Set());
	}
}

export function selectAllFiles(): void {
	const files = get(folderFiles);
	pendingSelection.set(new Set(files));
}

export function clearSelectedPath(): void {
	resetFiles();
}
