import { open } from '@tauri-apps/plugin-dialog';
import { readDir } from '@tauri-apps/plugin-fs';

/**
 * Opens a native file picker dialog to select an SDLXLIFF file.
 * @returns The selected file path or null if cancelled
 */
export async function selectSdlxliffFile(): Promise<string | null> {
	const result = await open({
		multiple: false,
		filters: [{ name: 'SDLXLIFF', extensions: ['sdlxliff'] }]
	});
	return result as string | null;
}

/**
 * Opens a native file picker dialog to select a folder.
 * @returns The selected folder path or null if cancelled
 */
export async function selectFolder(): Promise<string | null> {
	const result = await open({
		directory: true,
		multiple: false
	});
	return result as string | null;
}

/**
 * Scans a folder for SDLXLIFF files (non-recursive).
 * @param folderPath The folder to scan
 * @returns Array of full paths to .sdlxliff files found
 */
export async function findSdlxliffFiles(folderPath: string): Promise<string[]> {
	try {
		const entries = await readDir(folderPath);
		const sdlxliffFiles: string[] = [];

		for (const entry of entries) {
			if (entry.isFile && entry.name.toLowerCase().endsWith('.sdlxliff')) {
				// Construct full path
				const fullPath = folderPath.endsWith('/') || folderPath.endsWith('\\')
					? `${folderPath}${entry.name}`
					: `${folderPath}/${entry.name}`;
				sdlxliffFiles.push(fullPath);
			}
		}

		return sdlxliffFiles.sort();
	} catch (error) {
		console.error('Error scanning folder:', error);
		return [];
	}
}